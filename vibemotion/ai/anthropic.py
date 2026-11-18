"""Provider Anthropic (Claude) lewat Messages API."""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import AIError, Overloaded, RateLimited, read_image_b64

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, key: str, model: str, session: requests.Session | None = None,
                 timeout: int = 300, max_tokens: int = 16000):
        self.key, self.model, self.timeout, self.max_tokens = key, model, timeout, max_tokens
        self.http = session or requests.Session()
        self.last_usage: tuple[int, int] | None = None

    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str:
        if not self.key:
            raise AIError("API key Anthropic kosong.")
        content: list[dict] = []
        for img in images or []:
            mime, data = read_image_b64(img)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
        content.append({"type": "text", "text": user})
        payload = {"model": self.model, "max_tokens": self.max_tokens, "system": system,
                   "messages": [{"role": "user", "content": content}]}
        headers = {"x-api-key": self.key, "anthropic-version": VERSION, "content-type": "application/json"}
        last = ""
        for n in range(3):
            r = self.http.post(URL, json=payload, headers=headers, timeout=self.timeout)
            if r.status_code == 200:
                try:
                    data = r.json()
                    usage = data.get("usage") or {}
                    self.last_usage = (int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
                    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
                except (KeyError, ValueError, TypeError) as e:
                    raise AIError(f"Balasan Claude tidak terduga: {r.text[:300]}") from e
            last = f"{r.status_code}: {r.text[:300]}"
            if r.status_code in (529, 500, 502, 503):  # overloaded / server — coba lagi
                time.sleep(2 ** (n + 1))
                continue
            if r.status_code == 429:
                raise RateLimited(last)
            raise AIError(f"Claude {last}")
        raise Overloaded(f"Claude tidak tersedia: {last}")
