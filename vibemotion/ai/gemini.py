"""Provider Gemini (REST) dengan rotasi multi-key saat kena limit."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import requests

from .base import AIError, ModelNotFound, Overloaded, RateLimited, read_image_b64

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class KeyRing:
    def __init__(self, keys: list[str]):
        self.keys = [k.strip() for k in keys if k.strip()]
        self.index = 0

    def current(self) -> str:
        if not self.keys:
            raise AIError("API key Gemini kosong.")
        return self.keys[self.index % len(self.keys)]

    def rotate(self) -> str:
        self.index = (self.index + 1) % max(1, len(self.keys))
        return self.current()


def is_limit_error(status: int, body: str) -> bool:
    low = body.lower()
    return status == 429 or "resource_exhausted" in low or "quota" in low or "rate limit" in low


class GeminiProvider:
    def __init__(self, keys: list[str], model: str, on_log: Callable[[str], None] | None = None,
                 session: requests.Session | None = None, timeout: int = 180,
                 fallback_models: list[str] | None = None, max_output_tokens: int | None = None):
        self.ring, self.model, self.timeout = KeyRing(keys), model, timeout
        self.max_output_tokens = max_output_tokens
        self.last_usage: tuple[int, int] | None = None
        self.fallbacks = [m.strip() for m in (fallback_models or []) if m.strip() and m.strip() != model]
        self.on_log = on_log or (lambda _m: None)
        self.http = session or requests.Session()

    def _call(self, key: str, payload: dict, model: str) -> str:
        r = self.http.post(API.format(model=model), params={"key": key}, json=payload, timeout=self.timeout)
        if r.status_code != 200:
            if is_limit_error(r.status_code, r.text):
                raise RateLimited(r.text[:300])
            if r.status_code == 404:
                raise ModelNotFound(f"Gemini 404: {r.text[:300]}")
            if r.status_code >= 500:
                raise Overloaded(f"server {r.status_code}")
            raise AIError(f"Gemini {r.status_code}: {r.text[:400]}")
        try:
            data = r.json()
            meta = data.get("usageMetadata") or {}
            self.last_usage = (int(meta.get("promptTokenCount", 0)),
                               int(meta.get("candidatesTokenCount", 0)) + int(meta.get("thoughtsTokenCount", 0)))
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError) as e:
            raise AIError(f"Balasan Gemini tidak terduga: {r.text[:300]}") from e

    def _try_model(self, model: str, payload: dict, attempts: int) -> str:
        last: Exception | None = None
        for n in range(attempts):
            try:
                return self._call(self.ring.current(), payload, model)
            except RateLimited as e:
                last = e
                self.on_log(f"[Gemini] limit → pindah ke key #{(self.ring.index + 1) % len(self.ring.keys) + 1}")
                self.ring.rotate()
            except Overloaded as e:
                last = e
                if n < attempts - 1:
                    self.on_log(f"[Gemini] {model}: {e}, coba lagi… ({n + 1}/{attempts})")
                    time.sleep(min(2 ** (n + 1), 20))
        msg = f"Semua key/percobaan gagal: {last}"
        raise (RateLimited(msg) if isinstance(last, RateLimited) else Overloaded(msg))

    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str:
        parts: list[dict] = [{"text": user}]
        for img in images or []:
            mime, data = read_image_b64(img)
            parts.append({"inline_data": {"mime_type": mime, "data": data}})
        payload = {"system_instruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": parts}]}
        if self.max_output_tokens:
            payload["generationConfig"] = {"maxOutputTokens": self.max_output_tokens}
        models = [self.model, *self.fallbacks]
        for i, model in enumerate(models):
            attempts = (max(1, len(self.ring.keys)) + 4) if i == 0 else 2  # cadangan: cepat menyerah
            try:
                return self._try_model(model, payload, attempts)
            except ModelNotFound:
                if i == 0:
                    raise  # model utama salah: itu kesalahan pengaturan, jangan ditutupi
                self.on_log(f"[Gemini] model cadangan {model} tidak tersedia, dilewati")
            except (Overloaded, RateLimited):
                if i == len(models) - 1:
                    raise
                self.on_log(f"[Gemini] {model} sibuk → mencoba model cadangan {models[i + 1]}")
        raise Overloaded("Semua model Gemini tidak tersedia")
