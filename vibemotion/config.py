"""Pengaturan aplikasi + penyimpanan JSON."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .core.fsutil import atomic_write
from .core import secrets
from .core.paths import app_data_dir, default_export_dir, default_project_dir


@dataclass
class Settings:
    language: str = "id"  # "id" | "en"
    provider: str = "gemini"  # "gemini" | "anthropic" | "openai"
    gemini_keys: list[str] = field(default_factory=list)
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallbacks: list[str] = field(default_factory=lambda: ["gemini-2.5-flash-lite"])  # dicoba bila model utama sibuk
    fallback_provider: str = "none"  # "none" | "gemini" | "anthropic" | "openai": dipakai bila provider utama sibuk
    anthropic_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    openai_base_url: str = "https://openrouter.ai/api/v1"
    openai_key: str = ""
    openai_model: str = "google/gemini-2.5-flash"
    project_dir: str = str(default_project_dir())
    export_dir: str = str(default_export_dir())
    # default output
    ratio: str = "16:9"
    fps: int = 30
    duration_sec: float = 10.0
    render_format: str = "mp4"
    hardware_acceleration: str = "if-possible"  # disable | if-possible | required
    concurrency: int = 0  # 0 = otomatis (Remotion memilih)
    last_instruction: str = ""
    update_url: str = ""  # repo GitHub (https://github.com/owner/repo) atau URL JSON
    check_updates: bool = True
    price_in: float = 0.0   # USD per 1 juta token masuk (opsional, untuk menampilkan perkiraan biaya)
    price_out: float = 0.0  # USD per 1 juta token keluar
    onboarded: bool = False  # panduan pertama kali sudah ditutup
    auto_check: bool = True  # validasi + perbaikan otomatis kode AI
    visual_review: bool = False  # tinjauan visual (render frame → AI menilai); lebih lambat/mahal

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or cls.path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        defaults = cls()
        clean = {}
        for f in fields(cls):
            if f.name not in raw:
                continue
            value, default = raw[f.name], getattr(defaults, f.name)
            if isinstance(default, bool) or not isinstance(default, (int, float, str, list)):
                ok = isinstance(value, type(default))
            elif isinstance(default, (int, float)):  # angka: terima angka (bukan bool) atau string angka
                try:
                    value, ok = type(default)(value), not isinstance(value, bool)
                except (TypeError, ValueError):
                    ok = False
            else:
                ok = isinstance(value, type(default))
            if ok and isinstance(default, list):
                ok = all(isinstance(x, str) for x in value)
            if ok:
                clean[f.name] = value
        lost = False
        for name in ("anthropic_key", "openai_key"):
            if name in clean:
                clean[name], ok = secrets.unprotect(clean[name])
                lost |= not ok
        if "gemini_keys" in clean:
            keys = []
            for k in clean["gemini_keys"]:
                text, ok = secrets.unprotect(k)
                lost |= not ok
                if text:
                    keys.append(text)
            clean["gemini_keys"] = keys
        obj = cls(**clean)
        obj.secrets_lost = lost  # bukan field: tidak ikut tersimpan
        return obj

    def save(self, path: Path | None = None) -> None:
        path = path or self.path()
        data = asdict(self)
        data["anthropic_key"] = secrets.protect(self.anthropic_key)
        data["openai_key"] = secrets.protect(self.openai_key)
        data["gemini_keys"] = [secrets.protect(k) for k in self.gemini_keys]
        atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False))

    def active_key_count(self) -> int:
        if self.provider == "gemini":
            return len(self.gemini_keys)
        return int(bool(self.anthropic_key if self.provider == "anthropic" else self.openai_key))


RATIOS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "2:3": (1080, 1620),
    "21:9": (2560, 1080),
}
