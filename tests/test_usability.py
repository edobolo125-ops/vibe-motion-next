import pytest

from vibemotion.ai.anthropic import AnthropicProvider
from vibemotion.ai.base import AIError
from vibemotion.ai.connection import check_connection
from vibemotion.ai.gemini import GeminiProvider
from vibemotion.ai.openai_compat import OpenAICompatProvider
from vibemotion.ai.service import FallbackProvider, make_provider
from vibemotion.ai.usage import MeteredProvider, UsageMeter, fmt_tokens
from vibemotion.config import Settings
from vibemotion.core import env_setup
from vibemotion.core.onboarding import all_ready, check_steps
from vibemotion.core.project import Project


class Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._d, self.text = status, data, text or str(data)
    def json(self): return self._d


class Http:
    def __init__(self, *r): self.r, self.sent = list(r), []
    def post(self, url, **kw): self.sent.append((url, kw)); return self.r.pop(0)


# ---------- penggunaan token ----------
def test_fmt_tokens():
    assert [fmt_tokens(n) for n in (0, 999, 1000, 12_340, 2_500_000)] == ["0", "999", "1.0k", "12.3k", "2.50M"]


def test_meter_totals_cost_and_listeners():
    m = UsageMeter(price_in=0.5, price_out=2.0)
    seen = []
    m.listeners.append(lambda: seen.append(m.requests))
    m.listeners.append(lambda: 1 / 0)  # listener rusak tidak boleh menggagalkan
    m.add(1000, 500); m.add(2000, 100)
    assert (m.input_tokens, m.output_tokens, m.requests, m.last_in, m.last_out) == (3000, 600, 2, 2000, 100) and seen == [1, 2]
    assert m.cost == pytest.approx((3000 * 0.5 + 600 * 2.0) / 1e6)
    assert m.last_cost == pytest.approx((2000 * 0.5 + 100 * 2.0) / 1e6)
    assert "Sesi: 3.0k masuk" in m.summary("id") and "≈ $" in m.summary("id") and "session: 3.0k in" in m.summary("en")


def test_meter_hides_cost_without_prices_and_empty_when_unused():
    m = UsageMeter(); assert m.summary() == "" and m.cost is None
    m.add(10, 5); assert "≈" not in m.summary() and m.last_cost is None


def test_gemini_reports_usage_including_thinking_tokens():
    ok = Resp(200, {"candidates": [{"content": {"parts": [{"text": "hai"}]}}],
                    "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50}})
    g = GeminiProvider(["k"], "m", session=Http(ok)); assert g.complete("s", "u") == "hai" and g.last_usage == (120, 80)


def test_anthropic_and_openai_report_usage():
    a = AnthropicProvider("k", "m", session=Http(Resp(200, {"content": [{"type": "text", "text": "x"}], "usage": {"input_tokens": 7, "output_tokens": 3}})))
    a.complete("s", "u"); assert a.last_usage == (7, 3)
    o = OpenAICompatProvider("http://x", "k", "m", session=Http(Resp(200, {"choices": [{"message": {"content": "y"}}], "usage": {"prompt_tokens": 9, "completion_tokens": 4}})))
    o.complete("s", "u"); assert o.last_usage == (9, 4)


def test_missing_usage_is_tolerated():
    g = GeminiProvider(["k"], "m", session=Http(Resp(200, {"candidates": [{"content": {"parts": [{"text": "z"}]}}]})))
    assert g.complete("s", "u") == "z" and g.last_usage == (0, 0)


def test_metered_provider_records_and_fallback_forwards_usage():
    class P:
        last_usage = (11, 22)
        def complete(self, s, u, images=None): return "ok"
    m = UsageMeter(); assert MeteredProvider(P(), m).complete("s", "u") == "ok" and (m.input_tokens, m.output_tokens) == (11, 22)
    fb = FallbackProvider([("a", P())]); fb.complete("s", "u"); assert fb.last_usage == (11, 22)
    class Q:  # tanpa last_usage → tidak mencatat, tidak crash
        def complete(self, s, u, images=None): return "ok"
    m2 = UsageMeter(); MeteredProvider(Q(), m2).complete("s", "u"); assert m2.requests == 0


def test_make_provider_wraps_when_meter_given():
    s = Settings(provider="gemini", gemini_keys=["k"])
    assert isinstance(make_provider(s, None, UsageMeter()), MeteredProvider) and isinstance(make_provider(s), GeminiProvider)


def test_max_tokens_sent_only_when_set():
    ok = Resp(200, {"candidates": [{"content": {"parts": [{"text": "a"}]}}]})
    h1 = Http(ok); GeminiProvider(["k"], "m", session=h1, max_output_tokens=512).complete("s", "u")
    assert h1.sent[0][1]["json"]["generationConfig"] == {"maxOutputTokens": 512}
    h2 = Http(ok); GeminiProvider(["k"], "m", session=h2).complete("s", "u"); assert "generationConfig" not in h2.sent[0][1]["json"]
    h3 = Http(Resp(200, {"choices": [{"message": {"content": "a"}}]}))
    OpenAICompatProvider("http://x", "k", "m", session=h3, max_tokens=64).complete("s", "u"); assert h3.sent[0][1]["json"]["max_tokens"] == 64


# ---------- tes koneksi ----------
def patch_single(monkeypatch, provider=None, error=None):
    import vibemotion.ai.connection as c
    def fake(s, name, on_log, max_tokens=None, **kw):
        fake.args = (name, max_tokens)
        fake.kw = kw
        if error: raise error
        return provider
    monkeypatch.setattr(c, "_single", fake)
    return fake


def test_connection_ok_reports_provider_model_and_reply(monkeypatch):
    class P:
        def complete(self, s, u, images=None): return "OK\n"
    f = patch_single(monkeypatch, P())
    r = check_connection(Settings(provider="gemini", gemini_model="gemini-x"))
    assert r.ok and "gemini (gemini-x)" in r.message and "“OK”" in r.message and f.args == ("gemini", 512)
    assert check_connection(Settings(anthropic_model="claude-z"), "anthropic").message.startswith("✔ anthropic (claude-z)") and f.args == ("anthropic", 32)
    assert "responds in" in check_connection(Settings(language="en")).message


@pytest.mark.parametrize("err,needle", [(AIError("Claude 400: Your credit balance is too low"), "Saldo kredit"),
                                        (AIError("Gemini 400: API_KEY_INVALID"), "API key tidak valid"),
                                        (AIError("Gemini 404: no longer available"), "Refresh"),
                                        (AIError("API key Gemini kosong. Isi di tab Pengaturan."), "kosong")])
def test_connection_failures_are_explained(monkeypatch, err, needle):
    patch_single(monkeypatch, error=err)
    r = check_connection(Settings())
    assert not r.ok and needle in r.message


def test_connection_real_provider_empty_key():
    r = check_connection(Settings(provider="gemini", gemini_keys=[]))
    assert not r.ok and "kosong" in r.message


# ---------- onboarding ----------
def test_onboarding_steps(monkeypatch, tmp_path):
    p = Project(tmp_path)
    monkeypatch.setattr(env_setup, "node_version", lambda: None)
    steps = {s.key: s for s in check_steps(Settings(), p)}
    assert not steps["node"].ok and not steps["key"].ok and not steps["env"].ok and not all_ready(list(steps.values()))
    monkeypatch.setattr(env_setup, "node_version", lambda: "v24.1.0")
    (tmp_path / "node_modules" / "remotion").mkdir(parents=True); (tmp_path / "package.json").write_text("{}")
    steps = check_steps(Settings(provider="anthropic", anthropic_key="sk"), p)
    assert all_ready(steps) and steps[0].detail == "v24.1.0"
    assert [s.key for s in steps] == ["node", "key", "env"]


def test_new_settings_defaults_and_roundtrip(tmp_path):
    s = Settings(); assert s.onboarded is False and s.price_in == 0.0 and s.price_out == 0.0
    f = tmp_path / "c.json"; Settings(price_in=0.3, price_out=2.5, onboarded=True).save(f)
    t = Settings.load(f); assert (t.price_in, t.price_out, t.onboarded) == (0.3, 2.5, True)


def test_connection_test_uses_short_timeout_and_no_fallback_models(monkeypatch):
    class P:
        def complete(self, s, u, images=None): return "OK"
    f = patch_single(monkeypatch, P())
    assert check_connection(Settings()).ok
    assert f.kw == {"timeout": 45, "for_test": True}  # tes koneksi: tidak menggantung 3 menit, hanya model yang dipilih
