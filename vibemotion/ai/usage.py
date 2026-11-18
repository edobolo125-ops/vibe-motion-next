"""Penghitung pemakaian token dari angka NYATA yang dikembalikan API (bukan perkiraan)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


@dataclass
class UsageMeter:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    last_in: int = 0
    last_out: int = 0
    price_in: float = 0.0   # USD per 1 juta token (diisi pengguna; kosong = biaya tidak ditampilkan)
    price_out: float = 0.0
    listeners: list[Callable[[], None]] = field(default_factory=list)

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.input_tokens += tokens_in
        self.output_tokens += tokens_out
        self.last_in, self.last_out = tokens_in, tokens_out
        self.requests += 1
        for fn in list(self.listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001 — tampilan tidak boleh menggagalkan permintaan AI
                pass

    def _cost(self, i: int, o: int) -> float | None:
        if not (self.price_in or self.price_out):
            return None
        return (i * self.price_in + o * self.price_out) / 1_000_000

    @property
    def cost(self) -> float | None:
        return self._cost(self.input_tokens, self.output_tokens)

    @property
    def last_cost(self) -> float | None:
        return self._cost(self.last_in, self.last_out)

    def summary(self, lang: str = "id") -> str:
        if not self.requests:
            return ""
        word = ("in", "out", "last", "session") if lang == "en" else ("masuk", "keluar", "terakhir", "Sesi")
        text = (f"{word[3]}: {fmt_tokens(self.input_tokens)} {word[0]} · {fmt_tokens(self.output_tokens)} {word[1]}"
                f" · {word[2]} {fmt_tokens(self.last_in)}/{fmt_tokens(self.last_out)}")
        if self.cost is not None:
            text += f" · ≈ ${self.cost:.3f}"
        return text


class MeteredProvider:
    """Membungkus provider; setelah tiap panggilan sukses mencatat `last_usage` ke meter."""

    def __init__(self, inner, meter: UsageMeter):
        self.inner, self.meter = inner, meter

    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str:
        text = self.inner.complete(system, user, images)
        usage = getattr(self.inner, "last_usage", None)
        if usage:
            self.meter.add(int(usage[0]), int(usage[1]))
        return text
