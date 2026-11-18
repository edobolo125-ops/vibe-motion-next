"""Pustaka pribadi pengguna: prompt tersimpan dan template buatan sendiri (di folder data aplikasi)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .fsutil import atomic_write
from .paths import app_data_dir

MAX_PROMPTS = 100
MAX_TEXT = 20_000
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class SavedPrompts:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else app_data_dir() / "prompts.json"

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def names(self) -> list[str]:
        return sorted(self._read(), key=str.lower)

    def get(self, name: str) -> str:
        return self._read()[name]

    def save(self, name: str, text: str) -> None:
        name, text = name.strip()[:60], text.strip()
        if not name or not text:
            raise ValueError("Nama dan isi prompt tidak boleh kosong.")
        data = self._read()
        if name not in data and len(data) >= MAX_PROMPTS:
            raise ValueError(f"Maksimal {MAX_PROMPTS} prompt tersimpan.")
        data[name] = text[:MAX_TEXT]
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False))

    def delete(self, name: str) -> bool:
        data = self._read()
        if name not in data:
            return False
        del data[name]
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False))
        return True


@dataclass(frozen=True)
class UserTemplate:
    key: str
    name: str
    seconds: float
    code: str


class UserTemplates:
    def __init__(self, directory: Path | None = None):
        self.dir = Path(directory) if directory else app_data_dir() / "templates"

    def _key(self, name: str) -> str:
        return _SAFE.sub("_", name.strip())[:50].strip("_") or "template"

    def save(self, name: str, code: str, seconds: float = 5.0) -> UserTemplate:
        name = name.strip()[:60]
        if not name or not code.strip():
            raise ValueError("Nama dan kode template tidak boleh kosong.")
        key = self._key(name)
        atomic_write(self.dir / f"{key}.tsx", code)
        atomic_write(self.dir / f"{key}.json", json.dumps({"name": name, "seconds": float(seconds)}, ensure_ascii=False))
        return UserTemplate(key, name, float(seconds), code)

    def list(self) -> list[UserTemplate]:
        out = []
        if not self.dir.exists():
            return out
        for meta in sorted(self.dir.glob("*.json")):
            try:
                info = json.loads(meta.read_text(encoding="utf-8"))
                code = meta.with_suffix(".tsx").read_text(encoding="utf-8")
                out.append(UserTemplate(meta.stem, str(info["name"]), float(info.get("seconds", 5.0)), code))
            except (OSError, ValueError, KeyError, TypeError):
                continue  # entri rusak dilewati
        return sorted(out, key=lambda t: t.name.lower())

    def delete(self, key: str) -> bool:
        removed = False
        for ext in (".tsx", ".json"):
            f = self.dir / (Path(key).name + ext)  # .name: cegah path traversal
            if f.exists():
                f.unlink()
                removed = True
        return removed
