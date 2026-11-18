"""Riwayat versi per video: snapshot kode bertanda waktu di <proyek>/.vm_history/<video>/."""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .fsutil import atomic_write

MAX_PER_VIDEO = 30
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Entry:
    id: str  # nama file
    label: str
    timestamp: float
    size: int

    @property
    def when(self) -> str:
        return time.strftime("%d %b %H:%M:%S", time.localtime(self.timestamp))


class History:
    def __init__(self, root: Path, limit: int = MAX_PER_VIDEO):
        self.root, self.limit = Path(root) / ".vm_history", limit
        self._lock = threading.RLock()  # snapshot dipanggil dari thread UI dan thread AI

    def _dir(self, video_id: str) -> Path:
        return self.root / _SAFE.sub("_", video_id)

    def list(self, video_id: str) -> list[Entry]:
        d = self._dir(video_id)
        if not d.exists():
            return []
        out = []
        for f in d.glob("*.tsx"):
            try:
                stamp, _, label = f.stem.partition("__")
                out.append(Entry(f.name, label.replace("_", " ") or "versi", int(stamp.split("-")[0]) / 1000, f.stat().st_size))
            except (ValueError, OSError):
                continue
        return sorted(out, key=lambda e: e.id, reverse=True)  # terbaru dulu

    def read(self, video_id: str, entry_id: str) -> str:
        path = (self._dir(video_id) / Path(entry_id).name)  # .name: cegah path traversal
        return path.read_text(encoding="utf-8")

    def snapshot(self, video_id: str, code: str, label: str = "manual") -> Entry | None:
        """Simpan versi; None bila kode sama dengan versi terbaru."""
        with self._lock:
            entries = self.list(video_id)
            if entries and self.read(video_id, entries[0].id) == code:
                return None
            d = self._dir(video_id)
            d.mkdir(parents=True, exist_ok=True)
            newest = max((int(e.id.partition("__")[0]) for e in entries), default=0)
            ms = max(int(time.time() * 1000), newest + 1)  # selalu lebih besar dari yang terakhir → urutan & nama unik
            name = f"{ms}__{_SAFE.sub('_', label)[:30] or 'versi'}.tsx"
            atomic_write(d / name, code)
            for old in self.list(video_id)[self.limit:]:
                try:
                    (d / old.id).unlink()
                except OSError:
                    pass
            return self.list(video_id)[0]
