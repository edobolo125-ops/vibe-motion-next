import pytest

from vibemotion.ai.base import AIError, ModelNotFound, Overloaded, RateLimited
from vibemotion.ai.gemini import GeminiProvider
from vibemotion.ai.anthropic import AnthropicProvider
from vibemotion.ai.openai_compat import OpenAICompatProvider
from vibemotion.ai.service import FallbackProvider, make_provider
from vibemotion.config import Settings
from vibemotion.core.errors import friendly_message


class Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._d, self.text = status, data, text or str(data)
    def json(self): return self._d


OK = lambda t: Resp(200, {"candidates": [{"content": {"parts": [{"text": t}]}}]})


class Http:
    """Merekam URL (model) tiap panggilan; respons per model."""
    def __init__(self, by_model):
        self.by_model, self.models = {k: list(v) for k, v in by_model.items()}, []
    def post(self, url, **kw):
        model = url.split("/models/")[1].split(":")[0]
        self.models.append(model)
        return self.by_model[model].pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)


def gem(http, fallbacks, logs=None):
    return GeminiProvider(["k"], "utama", logs.append if logs is not None else None, session=http, fallback_models=fallbacks)


def test_busy_primary_falls_back_to_backup_model():
    logs = []
    http = Http({"utama": [Resp(503, text="x")] * 5, "cadangan": [OK("dari cadangan")]})
    assert gem(http, ["cadangan"], logs).complete("s", "u") == "dari cadangan"
    assert http.models == ["utama"] * 5 + ["cadangan"] and any("model cadangan cadangan" in l for l in logs)


def test_505_and_500_are_treated_as_server_busy():
    for code in (500, 502, 505):
        http = Http({"utama": [Resp(code, text="x")] * 5, "cad": [OK("ok")]})
        assert gem(http, ["cad"]).complete("s", "u") == "ok"


def test_primary_recovers_without_touching_backup():
    http = Http({"utama": [Resp(503), OK("pulih")], "cad": []})
    assert gem(http, ["cad"]).complete("s", "u") == "pulih" and http.models == ["utama", "utama"]


def test_primary_model_404_is_config_error_not_hidden():
    http = Http({"utama": [Resp(404, text="no longer available")], "cad": [OK("x")]})
    with pytest.raises(ModelNotFound):
        gem(http, ["cad"]).complete("s", "u")
    assert http.models == ["utama"]


def test_missing_backup_is_skipped_and_chain_continues():
    http = Http({"utama": [Resp(503)] * 5, "a": [Resp(404, text="x")], "b": [OK("dari b")]})
    logs = []
    assert gem(http, ["a", "b"], logs).complete("s", "u") == "dari b" and any("a tidak tersedia" in l for l in logs)


def test_all_models_busy_raises_overloaded():
    http = Http({"utama": [Resp(503)] * 5, "cad": [Resp(503)] * 2})
    with pytest.raises(Overloaded, match="503"):
        gem(http, ["cad"]).complete("s", "u")
    assert http.models.count("cad") == 2  # cadangan hanya 2 percobaan


def test_backup_equal_to_primary_is_ignored():
    assert GeminiProvider(["k"], "m", fallback_models=["m", " ", "n"]).fallbacks == ["n"]


# ---------- FallbackProvider ----------
class P:
    def __init__(self, result): self.result, self.calls = result, 0
    def complete(self, s, u, images=None):
        self.calls += 1
        if isinstance(self.result, Exception): raise self.result
        return self.result


def test_provider_fallback_on_overload_ratelimit_and_network():
    for err in (Overloaded("x"), RateLimited("y"), __import__("requests").ConnectionError("net")):
        a, b = P(err), P("dari-b")
        logs = []
        assert FallbackProvider([("gemini", a), ("anthropic", b)], logs.append).complete("s", "u") == "dari-b"
        assert a.calls == b.calls == 1 and logs and "beralih ke anthropic" in logs[0]


def test_config_errors_are_not_hidden_by_fallback():
    a, b = P(AIError("API key salah")), P("tidak dipakai")
    with pytest.raises(AIError, match="API key salah"):
        FallbackProvider([("gemini", a), ("anthropic", b)]).complete("s", "u")
    assert b.calls == 0


def test_both_providers_failing_reports_original_problem():
    first, second = Overloaded("gemini sibuk"), Overloaded("claude sibuk")
    with pytest.raises(Overloaded, match="gemini sibuk"):
        FallbackProvider([("g", P(first)), ("c", P(second))]).complete("s", "u")
    with pytest.raises(Overloaded, match="gemini sibuk"):  # cadangan kena error pengaturan → tetap laporkan yang awal
        FallbackProvider([("g", P(first)), ("c", P(AIError("key claude salah")))]).complete("s", "u")


def test_make_provider_wires_fallbacks():
    s = Settings(provider="gemini", gemini_keys=["k"], anthropic_key="sk-ant", fallback_provider="anthropic",
                 gemini_fallbacks=["flash-lite"])
    p = make_provider(s)
    assert isinstance(p, FallbackProvider) and [n for n, _ in p.providers] == ["gemini", "anthropic"]
    assert isinstance(p.providers[0][1], GeminiProvider) and p.providers[0][1].fallbacks == ["flash-lite"]
    assert isinstance(p.providers[1][1], AnthropicProvider)
    # cadangan tanpa key / sama dengan utama / "none" → provider tunggal
    assert isinstance(make_provider(Settings(provider="gemini", gemini_keys=["k"], fallback_provider="anthropic")), GeminiProvider)
    assert isinstance(make_provider(Settings(provider="gemini", gemini_keys=["k"], fallback_provider="gemini")), GeminiProvider)
    assert isinstance(make_provider(Settings(provider="gemini", gemini_keys=["k"])), GeminiProvider)
    with pytest.raises(AIError):
        make_provider(Settings(provider="gemini"))


def test_other_providers_raise_overloaded_on_5xx(monkeypatch, tmp_path):
    class H:
        def __init__(self, *r): self.r = list(r)
        def post(self, *a, **k): return self.r.pop(0)
    with pytest.raises(Overloaded):
        OpenAICompatProvider("http://x", "k", "m", session=H(Resp(503, text="x"))).complete("s", "u")
    with pytest.raises(Overloaded):
        AnthropicProvider("k", "m", session=H(*[Resp(529, text="over")] * 3)).complete("s", "u")


def test_defaults_and_roundtrip(tmp_path):
    s = Settings(); assert s.gemini_fallbacks == ["gemini-2.5-flash-lite"] and s.fallback_provider == "none"
    f = tmp_path / "c.json"; Settings(gemini_fallbacks=["a", "b"], fallback_provider="openai").save(f)
    t = Settings.load(f); assert t.gemini_fallbacks == ["a", "b"] and t.fallback_provider == "openai"


@pytest.mark.parametrize("raw", ["Gemini 505: HTTP Version Not Supported", "Semua key/percobaan gagal: server 503",
                                  "Claude tidak tersedia: 529: overloaded", "Semua model Gemini tidak tersedia", "server 502"])
def test_friendly_server_busy_variants(raw):
    assert "sibuk" in friendly_message(raw, "id")


def test_friendly_does_not_misread_other_numbers():
    msg = friendly_message("Gemini 400: maximum 512 tokens exceeded", "id")
    assert "sibuk" not in msg
