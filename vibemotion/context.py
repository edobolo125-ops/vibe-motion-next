"""Konteks bersama antar tab: settings, proyek, preview, bus thread→UI."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, Callable

from .ai.usage import UsageMeter
from .config import Settings
from .core.preview import PreviewServer
from .core.project import Project
from .core.logs import get_logger
from .i18n import translate

log = get_logger("ui")


class UiBus:
    """Jalankan pekerjaan berat di thread, hasilnya dikembalikan ke thread UI (tkinter tidak thread-safe)."""

    def __init__(self, widget: Any, interval_ms: int = 60):
        self.widget, self.interval = widget, interval_ms
        self.q: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.widget.after(self.interval, self._poll)

    def _poll(self) -> None:
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:  # jangan sampai polling mati
            log.exception("UI callback error: %s", e)
        self.widget.after(self.interval, self._poll)

    def post(self, fn: Callable[..., Any], *a: Any, **kw: Any) -> None:
        self.q.put(lambda: fn(*a, **kw))

    def run(self, work: Callable[[], Any], on_ok: Callable[[Any], None] | None = None,
            on_err: Callable[[Exception], None] | None = None) -> None:
        def target() -> None:
            try:
                result = work()
            except Exception as e:  # noqa: BLE001 — diteruskan ke UI
                log.error("background task failed: %s: %s", type(e).__name__, e, exc_info=True)
                if on_err:
                    self.post(on_err, e)
                return
            if on_ok:
                self.post(on_ok, result)

        threading.Thread(target=target, daemon=True).start()


class AppContext:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.project = Project(Path(settings.project_dir))
        self.project.load()
        self.bus: UiBus | None = None
        self.selected_id: str = self.project.items[0].id
        self.preview: PreviewServer | None = None
        self.last_error: str = ""
        self.autofix_attempts = 0
        self._video_listeners: list[Callable[[], None]] = []
        self._flushers: list[Callable[[], None]] = []
        self.log: Callable[[str], None] = lambda _m: None
        self.usage = UsageMeter(price_in=settings.price_in, price_out=settings.price_out)
        self.actions: dict[str, Callable[[], None]] = {}  # aksi lintas-tab, mis. "setup_env"
        self.show_tab: Callable[[str], None] = lambda _n: None

    def usage_changed(self) -> None:
        """Harga/bahasa berubah: segarkan tampilan ringkasan pemakaian."""
        for fn in list(self.usage.listeners):
            fn()

    def tr(self, key: str, **fmt: object) -> str:
        return translate(self.settings.language, key, **fmt)

    # --- proyek berubah (tambah/hapus/urut) ---
    def on_videos_changed(self, fn: Callable[[], None]) -> None:
        self._video_listeners.append(fn)

    def notify_videos_changed(self) -> None:
        if self.selected_id not in {i.id for i in self.project.items}:
            self.selected_id = self.project.items[0].id
        for fn in self._video_listeners:
            fn()

    # --- simpan editor yang belum tersimpan sebelum preview/render ---
    def register_flusher(self, fn: Callable[[], None]) -> None:
        self._flushers.append(fn)

    def flush(self) -> None:
        for fn in self._flushers:
            fn()
        self.project.save()

    def set_project_dir(self, path: str) -> None:
        self.settings.project_dir = path
        self.project = Project(Path(path))
        self.project.load()
        self.selected_id = self.project.items[0].id
        self.notify_videos_changed()

    @property
    def selected(self):
        return self.project.get(self.selected_id)
