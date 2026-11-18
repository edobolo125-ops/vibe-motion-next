"""Daftar model siap pakai + pengambilan daftar terbaru dari API tiap provider."""
from __future__ import annotations

import requests

# Preset awal (dipakai saat offline). Tombol Refresh di Pengaturan mengambil daftar terbaru dari API.
PRESETS: dict[str, list[str]] = {
    "anthropic": ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
    "gemini": ["gemini-4-argon", "gemini-3.8-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
    "openai": ["anthropic/claude-sonnet-5-5", "anthropic/claude-opus-5-5", "google/gemini-2.5-pro",
               "google/gemini-2.5-flash", "openai/gpt-5"],
}
_GEMINI_SKIP = ("embedding", "aqa", "tts", "imagen", "veo", "live", "native-audio", "robotics", "computer-use")


def merge(preset: list[str], fetched: list[str], current: str = "") -> list[str]:
    """Hasil API di depan (terbaru dulu), preset & model aktif tetap tersedia, tanpa duplikat."""
    out: list[str] = []
    for m in [*fetched, current, *preset]:
        if m and m not in out:
            out.append(m)
    return out


def fetch_models(provider: str, key: str, base_url: str = "", http: requests.Session | None = None) -> list[str]:
    http = http or requests.Session()
    if not key:
        raise ValueError("API key kosong.")
    if provider == "gemini":
        r = http.get("https://generativelanguage.googleapis.com/v1beta/models",
                     params={"key": key, "pageSize": 200}, timeout=30)
        _check(r)
        names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        names = [n for n in names if n.startswith("gemini") and not any(s in n for s in _GEMINI_SKIP)]
        return sorted(names, reverse=True)
    if provider == "anthropic":
        r = http.get("https://api.anthropic.com/v1/models", params={"limit": 100},
                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=30)
        _check(r)
        return [m["id"] for m in r.json().get("data", [])]  # API mengurutkan terbaru dulu
    if provider == "openai":
        r = http.get(base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
        _check(r)
        return sorted((m["id"] for m in r.json().get("data", [])), reverse=True)
    raise ValueError(f"provider tidak dikenal: {provider}")


def _check(r: requests.Response) -> None:
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
