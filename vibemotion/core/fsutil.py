"""Penulisan file atomik: tulis ke berkas sementara lalu ganti, supaya crash/mati lampu tidak merusak file."""
from __future__ import annotations

import os
from pathlib import Path


def atomic_write(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding=encoding, newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
