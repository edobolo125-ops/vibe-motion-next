from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Protocol


class AIError(RuntimeError):
    pass


class RateLimited(AIError):
    """Kuota / 429 — pemanggil boleh mencoba key lain."""


class Overloaded(AIError):
    """Server sibuk/tidak tersedia setelah dicoba ulang — pemanggil boleh beralih ke cadangan."""


class TimedOut(Overloaded):
    """Koneksi tersambung tetapi server tidak menjawab tepat waktu (model lambat/sibuk) — bukan masalah internet."""


class ModelNotFound(AIError):
    """Model tidak ada / tidak tersedia untuk akun ini (HTTP 404)."""


class Provider(Protocol):
    def complete(self, system: str, user: str, images: list[Path] | None = None) -> str: ...


def read_image_b64(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return mime, base64.b64encode(Path(path).read_bytes()).decode()
