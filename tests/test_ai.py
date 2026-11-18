import pytest

from vibemotion.ai.base import AIError
from vibemotion.ai.gemini import GeminiProvider, KeyRing, is_limit_error
from vibemotion.ai.openai_compat import OpenAICompatProvider
from vibemotion.ai.prompts import GenerationSpec, build_system_prompt
from vibemotion.ai.service import AIService
from vibemotion.ai import skills


class Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._d, self.text = status, data, text or str(data)

    def json(self):
        return self._d


class FakeHTTP:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)

    def get(self, url, **kw):
        self.calls.append(url)
        return self.responses.pop(0)


OK = lambda t: Resp(200, {"candidates": [{"content": {"parts": [{"text": t}]}}]})


def test_keyring_rotation():
    r = KeyRing([" a ", "", "b"])
    assert r.keys == ["a", "b"] and r.current() == "a" and r.rotate() == "b" and r.rotate() == "a"
    with pytest.raises(AIError):
        KeyRing([]).current()


def test_limit_detection():
    assert is_limit_error(429, "") and is_limit_error(400, "RESOURCE_EXHAUSTED") and not is_limit_error(400, "bad")


def test_gemini_rotates_on_429_then_succeeds():
    http = FakeHTTP([Resp(429, text="quota"), OK("hello")])
    logs = []
    g = GeminiProvider(["k1", "k2"], "m", logs.append, session=http)
    assert g.complete("s", "u") == "hello"
    assert [c["params"]["key"] for c in http.calls] == ["k1", "k2"] and logs


def test_gemini_all_keys_limited():
    http = FakeHTTP([Resp(429, text="quota")] * 10)
    with pytest.raises(AIError):
        GeminiProvider(["k1", "k2"], "m", session=http).complete("s", "u")


def test_gemini_hard_error_not_retried():
    http = FakeHTTP([Resp(400, text="bad request")])
    with pytest.raises(AIError):
        GeminiProvider(["k"], "m", session=http).complete("s", "u")
    assert len(http.calls) == 1


def test_openai_payload_has_image(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"\x89PNG")
    http = FakeHTTP([Resp(200, {"choices": [{"message": {"content": "ok"}}]})])
    p = OpenAICompatProvider("http://x/v1/", "k", "m", session=http)
    assert p.complete("s", "u", [img]) == "ok"
    sent = http.calls[0]["json"]["messages"][1]["content"]
    assert sent[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert http.calls[0]["headers"]["Authorization"] == "Bearer k"


class StubProvider:
    def __init__(self, reply): self.reply, self.seen = reply, []
    def complete(self, system, user, images=None):
        self.seen.append((system, user)); return self.reply


def test_service_generate_edit_fix():
    stub = StubProvider("```tsx\nexport const Remotion = () => null;\n```")
    svc = AIService(stub, skills_loader=lambda: "SKILLTEXT")
    code = svc.generate(GenerationSpec(theme="neon", styles={"pacing": "Fast & punchy", "camera": "Auto"}), "buat intro")
    assert "export const Remotion" in code
    system = stub.seen[0][0]
    assert "neon" in system and "Fast & punchy" in system and "camera" not in system and "SKILLTEXT" in system
    svc.edit(code, "lebih cepat"); svc.fix(code, "Unexpected token")
    assert "KODE SAAT INI" in stub.seen[1][1] and "ERROR" in stub.seen[2][1]
    with pytest.raises(AIError):
        svc.generate(GenerationSpec(), "  ")
    with pytest.raises(AIError):
        AIService(StubProvider("maaf saya tidak bisa")).fix("x", "e")


def test_prompt_spec_numbers():
    p = build_system_prompt(GenerationSpec(width=1080, height=1920, fps=24, duration_sec=5, assets=["assets/a.png"]))
    assert "1080x1920" in p and "120 frame" in p and 'staticFile("assets/a.png")' in p


def test_skills_install_and_prompt(tmp_path):
    tree = Resp(200, {"tree": [{"type": "blob", "path": "skills/x/SKILL.md"}, {"type": "blob", "path": "README.md"}]})
    http = FakeHTTP([tree, Resp(200, text="# Do things")])
    names = skills.install_skill("https://github.com/own/rep", http, tmp_path)
    assert names == ["own__rep__skills__x"] and skills.list_skills(tmp_path) == names
    assert "Do things" in skills.skills_prompt(tmp_path)
    skills.remove_skill(names[0], tmp_path)
    assert skills.list_skills(tmp_path) == [] and skills.skills_prompt(tmp_path) == ""
    with pytest.raises(ValueError):
        skills.parse_repo("bukan repo")
    assert skills.parse_repo("own/rep.git") == ("own", "rep")


def test_anthropic_payload_and_retry(tmp_path, monkeypatch):
    from vibemotion.ai.anthropic import AnthropicProvider
    monkeypatch.setattr("time.sleep", lambda _s: None)
    img = tmp_path / "a.png"; img.write_bytes(b"\x89PNG")
    ok = Resp(200, {"content": [{"type": "text", "text": "hi"}, {"type": "thinking"}]})
    http = FakeHTTP([Resp(529, text="overloaded"), ok])
    p = AnthropicProvider("k", "claude-sonnet-5-5", session=http)
    assert p.complete("sys", "usr", [img]) == "hi" and len(http.calls) == 2
    sent = http.calls[0]
    assert sent["headers"]["x-api-key"] == "k" and sent["json"]["system"] == "sys"
    assert sent["json"]["messages"][0]["content"][0]["source"]["media_type"] == "image/png"
    with pytest.raises(AIError):
        AnthropicProvider("k", "m", session=FakeHTTP([Resp(400, text="bad")])).complete("s", "u")
    from vibemotion.ai.base import RateLimited
    with pytest.raises(RateLimited):
        AnthropicProvider("k", "m", session=FakeHTTP([Resp(429, text="x")])).complete("s", "u")


def test_make_provider_dispatch():
    from vibemotion.ai.anthropic import AnthropicProvider
    from vibemotion.ai.service import make_provider
    from vibemotion.config import Settings
    assert isinstance(make_provider(Settings(provider="anthropic", anthropic_key="k")), AnthropicProvider)
    with pytest.raises(AIError):
        make_provider(Settings(provider="anthropic"))


def test_fetch_models_and_merge():
    from vibemotion.ai.models import PRESETS, fetch_models, merge
    g = Resp(200, {"models": [
        {"name": "models/gemini-3-pro", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["generateContent"]}]})
    assert fetch_models("gemini", "k", http=FakeHTTP([g])) == ["gemini-3-pro", "gemini-2.5-flash"]
    a = Resp(200, {"data": [{"id": "claude-new"}, {"id": "claude-old"}]})
    assert fetch_models("anthropic", "k", http=FakeHTTP([a])) == ["claude-new", "claude-old"]
    assert fetch_models("openai", "k", "http://x/v1/", FakeHTTP([Resp(200, {"data": [{"id": "a"}, {"id": "b"}]})])) == ["b", "a"]
    with pytest.raises(ValueError):
        fetch_models("gemini", "")
    with pytest.raises(RuntimeError):
        fetch_models("anthropic", "k", http=FakeHTTP([Resp(401, text="no")]))
    m = merge(PRESETS["anthropic"], ["claude-new"], "custom-x")
    assert m[0] == "claude-new" and m[1] == "custom-x" and len(m) == len(set(m))


def test_gemini_retries_server_busy(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    http = FakeHTTP([Resp(503, text="overloaded")] * 3 + [OK("done")])
    assert GeminiProvider(["k"], "m", session=http).complete("s", "u") == "done" and len(http.calls) == 4
    with pytest.raises(AIError, match="503"):
        GeminiProvider(["k"], "m", session=FakeHTTP([Resp(503, text="x")] * 10)).complete("s", "u")
