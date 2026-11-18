from __future__ import annotations

from tkinter import messagebox

from ..core.errors import friendly_message
from ..core.logs import get_logger

log = get_logger("ui")


def show_error(ctx, error: object) -> None:
    """Catat ke log, tampilkan pesan ramah (+ detail teknis singkat)."""
    log.error("error shown: %s", error)
    messagebox.showerror(ctx.tr("err.title"), friendly_message(error, ctx.settings.language))
