"""Provider OpenAI-compatible (OpenAI, OpenRouter, LM Studio, dll)."""
from __future__ import annotations

from pathlib import Path

import requests

from .base import AIError, Overloaded, RateLimited, read_image_b64


class OpenAICompatProvider:
    def __init__(self, base_url: str, key: str, model: str,
                 session: requests.Session | None = None, timeout: int = 180, max_tokens: int | None = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.key, self.model, self.timeout = key, model, timeout
        self.http = session or requests.Session()
        self.max_tokens = max_tokens
        self.last_usage: tuple[int, int] | None = None

    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str:
        if not self.key:
            raise AIError("API key kosong.")
        content: list[dict] = [{"type": "text", "text": user}]
        for img in images or []:
            mime, data = read_image_b64(img)
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        payload = {"model": self.model,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        r = self.http.post(self.url, json=payload, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.key}"})
        if r.status_code == 429:
            raise RateLimited(r.text[:300])
        if r.status_code >= 500:
            raise Overloaded(f"server {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            raise AIError(f"{r.status_code}: {r.text[:400]}")
        try:
            data = r.json()
            usage = data.get("usage") or {}
            self.last_usage = (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise AIError(f"Balasan tidak terduga: {r.text[:300]}") from e
