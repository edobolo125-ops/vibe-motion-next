"""Fasad AI: generate / edit / auto-fix → kode TSX bersih."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config import Settings
from ..core.code_utils import clean_code_output, looks_like_component
from pathlib import Path

import requests

from .base import AIError, Overloaded, Provider, RateLimited
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider
from .prompts import EDIT_RULES, FIX_RULES, GenerationSpec, build_system_prompt
from .skills import skills_prompt
from .usage import MeteredProvider, UsageMeter


class FallbackProvider:
    """Coba provider berurutan; pindah ke berikutnya hanya untuk error sementara (sibuk/limit/jaringan)."""

    def __init__(self, providers: list[tuple[str, Provider]], on_log: Callable[[str], None] | None = None):
        self.providers = providers
        self.on_log = on_log or (lambda _m: None)
        self.last_usage: tuple[int, int] | None = None

    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str:
        first: Exception | None = None
        for i, (name, provider) in enumerate(self.providers):
            try:
                text = provider.complete(system, user, images)
                self.last_usage = getattr(provider, "last_usage", None)
                return text
            except (Overloaded, RateLimited, requests.RequestException) as e:
                first = first or e
                if i < len(self.providers) - 1:
                    self.on_log(f"[{name}] tidak tersedia ({type(e).__name__}) → beralih ke {self.providers[i + 1][0]}")
            except AIError as e:
                if first is not None:
                    raise first  # cadangan juga bermasalah: laporkan masalah awal
                raise  # kesalahan pengaturan (mis. key salah) jangan ditutupi
        assert first is not None
        raise first


def _single(s: Settings, name: str, on_log, max_tokens: int | None = None) -> Provider:
    if name == "gemini":
        if not s.gemini_keys:
            raise AIError("API key Gemini kosong. Isi di tab Pengaturan.")
        return GeminiProvider(s.gemini_keys, s.gemini_model, on_log, fallback_models=s.gemini_fallbacks,
                              max_output_tokens=max_tokens)
    if name == "anthropic":
        if not s.anthropic_key:
            raise AIError("API key Anthropic kosong. Isi di tab Pengaturan.")
        return AnthropicProvider(s.anthropic_key, s.anthropic_model, **({"max_tokens": max_tokens} if max_tokens else {}))
    if not s.openai_key:
        raise AIError("API key kosong. Isi di tab Pengaturan.")
    return OpenAICompatProvider(s.openai_base_url, s.openai_key, s.openai_model, max_tokens=max_tokens)


def model_name(s: Settings) -> str:
    """Nama model aktif dari provider utama."""
    return {"gemini": s.gemini_model, "anthropic": s.anthropic_model}.get(s.provider, s.openai_model)


def with_model(s: Settings, model: str) -> Settings:
    """Salinan Settings dengan model provider utama diganti (untuk perbandingan model)."""
    from dataclasses import replace
    field = {"gemini": "gemini_model", "anthropic": "anthropic_model"}.get(s.provider, "openai_model")
    return replace(s, **{field: model})


def _has_key(s: Settings, name: str) -> bool:
    return bool({"gemini": s.gemini_keys, "anthropic": s.anthropic_key, "openai": s.openai_key}.get(name))


def make_provider(s: Settings, on_log: Callable[[str], None] | None = None, meter: UsageMeter | None = None) -> Provider:
    primary = _single(s, s.provider, on_log)
    backup = s.fallback_provider
    provider: Provider = primary
    if backup in ("gemini", "anthropic", "openai") and backup != s.provider and _has_key(s, backup):
        provider = FallbackProvider([(s.provider, primary), (backup, _single(s, backup, on_log))], on_log)
    return MeteredProvider(provider, meter) if meter is not None else provider


class AIService:
    def __init__(self, provider: Provider, skills_loader: Callable[[], str] = skills_prompt):
        self.provider = provider
        self.skills_loader = skills_loader

    def _finish(self, raw: str) -> str:
        code = clean_code_output(raw)
        if not looks_like_component(code):
            raise AIError("Balasan AI bukan komponen Remotion yang valid.")
        return code

    def generate(self, spec: GenerationSpec, instruction: str, images: list[Path] | None = None) -> str:
        if not instruction.strip() and not images:
            raise AIError("Isi instruksi atau pilih gambar referensi.")
        system = build_system_prompt(spec, self.skills_loader())
        user = instruction.strip() or "Buat motion graphic yang menarik dari gambar referensi."
        return self._finish(self.provider.complete(system, user, images))

    def edit(self, code: str, request: str, spec: GenerationSpec | None = None,
             images: list[Path] | None = None) -> str:
        system = EDIT_RULES + ("\n" + build_system_prompt(spec, self.skills_loader()) if spec else "")
        user = f"KODE SAAT INI:\n{code}\n\nPERMINTAAN:\n{request}"
        return self._finish(self.provider.complete(system, user, images))

    def fix(self, code: str, error: str) -> str:
        user = f"KODE:\n{code}\n\nERROR:\n{error[:3000]}"
        return self._finish(self.provider.complete(FIX_RULES, user))
