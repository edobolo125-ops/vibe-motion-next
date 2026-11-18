"""Penulisan file atomik: tulis ke berkas sementara lalu ganti, supaya crash/mati lampu tidak merusak file."""
from __future__ import annotations

import os
import threading
from pathlib import Path


def atomic_write(path: Path | str, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # nama sementara unik per proses+thread: dua penulis ke berkas yang sama tidak saling menimpa berkas sementara
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
