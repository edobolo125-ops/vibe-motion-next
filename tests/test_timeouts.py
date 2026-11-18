import pytest
import requests

from vibemotion.ai.anthropic import AnthropicProvider
from vibemotion.ai.base import AIError, Overloaded, TimedOut
from vibemotion.ai.gemini import GeminiProvider
from vibemotion.ai.openai_compat import OpenAICompatProvider
from vibemotion.ai.service import FallbackProvider, _single
from vibemotion.config import Settings
from vibemotion.core.errors import friendly_message

OK = type("R", (), {"status_code": 200, "text": "", "json": lambda self: {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}})()


class Http:
    """Merekam model per panggilan; tiap model punya urutan hasil: 'timeout' atau respons."""
    def __init__(self, by_model): self.by, self.models, self.timeouts = {k: list(v) for k, v in by_model.items()}, [], []
    def post(self, url, **kw):
        m = url.split("/models/")[1].split(":")[0]; self.models.append(m); self.timeouts.append(kw.get("timeout"))
        r = self.by[m].pop(0)
        if r == "timeout": raise requests.ReadTimeout("Read timed out. (read timeout=180)")
        return r


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch): monkeypatch.setattr("time.sleep", lambda _s: None)


def gem(http, fallbacks=None, **kw): return GeminiProvider(["k"], "utama", session=http, fallback_models=fallbacks, **kw)


def test_timeout_is_retried_only_once_not_five_times():
    http = Http({"utama": ["timeout"] * 5})
    with pytest.raises(TimedOut, match="tidak ada jawaban"):
        gem(http).complete("s", "u")
    assert http.models == ["utama", "utama"]  # 2 percobaan saja (bukan 5 × 180 dtk)


def test_timeout_then_success_on_retry():
    http = Http({"utama": ["timeout", OK]})
    assert gem(http).complete("s", "u") == "ok" and http.models == ["utama", "utama"]


def test_timeout_falls_back_to_backup_model():
    http = Http({"utama": ["timeout", "timeout"], "ringan": [OK]})
    logs = []
    g = GeminiProvider(["k"], "utama", logs.append, session=http, fallback_models=["ringan"])
    assert g.complete("s", "u") == "ok" and http.models == ["utama", "utama", "ringan"] and any("sibuk" in l for l in logs)


def test_timed_out_is_a_subclass_of_overloaded_so_provider_fallback_works():
    assert issubclass(TimedOut, Overloaded) and issubclass(Overloaded, AIError)
    class Slow:
        def complete(self, s, u, images=None): raise TimedOut("lambat")
    class Fast:
        last_usage = None
        def complete(self, s, u, images=None): return "cepat"
    assert FallbackProvider([("gemini", Slow()), ("anthropic", Fast())]).complete("s", "u") == "cepat"


def test_other_providers_convert_timeout():
    def boom(*a, **k): raise requests.ReadTimeout("x")
    class H: post = staticmethod(boom)
    with pytest.raises(TimedOut): AnthropicProvider("k", "m", session=H()).complete("s", "u")
    with pytest.raises(TimedOut): OpenAICompatProvider("http://x", "k", "m", session=H()).complete("s", "u")


def test_single_passes_timeout_and_for_test_drops_fallbacks():
    s = Settings(provider="gemini", gemini_keys=["k"], gemini_fallbacks=["a", "b"])
    g = _single(s, "gemini", None, timeout=45, for_test=True)
    assert g.timeout == 45 and g.fallbacks == []
    g2 = _single(s, "gemini", None)
    assert g2.timeout == 180 and g2.fallbacks == ["a", "b"]
    assert _single(Settings(anthropic_key="k"), "anthropic", None, timeout=45).timeout == 45
    assert _single(Settings(openai_key="k"), "openai", None, timeout=45).timeout == 45


@pytest.mark.parametrize("raw", [
    "ReadTimeout: HTTPSConnectionPool(host='generativelanguage.googleapis.com', port=443): Read timed out. (read timeout=180)",
    "Semua key/percobaan gagal: tidak ada jawaban dalam 180 detik", "ConnectTimeout: x"])
def test_timeout_message_is_not_blamed_on_internet(raw):
    msg = friendly_message(raw, "id")
    assert "tidak menjawab" in msg and "Internet Anda baik-baik saja" in msg and "Tidak bisa terhubung" not in msg
    assert "does not respond" not in msg and "did not answer" in friendly_message(raw, "en")


def test_real_connection_failures_still_say_check_your_internet():
    for raw in ("ConnectionError: Max retries exceeded", "getaddrinfo failed"):
        assert "Tidak bisa terhubung" in friendly_message(raw, "id")
