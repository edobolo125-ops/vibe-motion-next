"""Tes koneksi satu klik: kirim permintaan minimal ke provider yang dipilih dan jelaskan hasilnya."""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..config import Settings
from ..core.errors import friendly_message
from .service import _single


TEST_TIMEOUT = 45  # detik; tes koneksi tidak boleh menggantung 3 menit


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # bukan kelas tes pytest
    ok: bool
    message: str
    seconds: float = 0.0


def _model_of(s: Settings, name: str) -> str:
    return {"gemini": s.gemini_model, "anthropic": s.anthropic_model}.get(name, s.openai_model)


def check_connection(settings: Settings, provider: str | None = None) -> TestResult:
    name = provider or settings.provider
    started = time.time()
    # token keluaran kecil → murah; Gemini diberi lebih longgar karena model "thinking" memakai token untuk berpikir
    limit = {"gemini": 512, "anthropic": 32}.get(name, 64)
    try:
        text = _single(settings, name, None, max_tokens=limit, timeout=TEST_TIMEOUT, for_test=True).complete("Balas hanya dengan satu kata: OK", "ping")
    except Exception as e:  # noqa: BLE001 — semua kegagalan dijelaskan ke pengguna
        return TestResult(False, friendly_message(e, settings.language), time.time() - started)
    took = time.time() - started
    reply = (text or "").strip().replace("\n", " ")[:40]
    word = "responds in" if settings.language == "en" else "merespons dalam"
    return TestResult(True, f"✔ {name} ({_model_of(settings, name)}) {word} {took:.1f} s" + (f' — “{reply}”' if reply else ""), took)
