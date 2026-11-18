"""Jendela utama: sidebar + tab."""
from __future__ import annotations

import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from . import __version__
from .config import Settings
from .context import AppContext, UiBus
from .core.logs import get_logger, log_dir, setup_logging
from .core.onboarding import all_ready, check_steps
from .core.updater import can_self_update, check_update, download_installer, launch_installer
from .resources import resource_path
from .ui.dialogs import show_error
from .ui.editor_tab import EditorTab
from .ui.generate_tab import GenerateTab
from .ui.run_tab import RunTab
from .ui.settings_tab import SettingsTab

APP_TITLE = "Vibe Motion Next"
log = get_logger("app")


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_TITLE}  v{__version__}")
        self.geometry("1240x800")
        self.minsize(1000, 640)

        self.ctx = AppContext(Settings.load())
        self.ctx.bus = UiBus(self)
        ctx = self.ctx

        sidebar = ctk.CTkFrame(self, width=170, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(sidebar, text="✦ Vibe Motion", font=ctk.CTkFont(size=17, weight="bold")).pack(pady=(18, 14))
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=12, pady=12)

        self.editor = EditorTab(self.content, ctx)
        self.tabs: dict[str, ctk.CTkFrame] = {
            "generate": GenerateTab(self.content, ctx),
            "editor": self.editor,
        }
        self.tabs["run"] = RunTab(self.content, ctx, self.editor)
        self.tabs["settings"] = SettingsTab(self.content, ctx)
        self.nav: dict[str, ctk.CTkButton] = {}
        for key in self.tabs:
            b = ctk.CTkButton(sidebar, text=ctx.tr(f"tab.{key}"), anchor="w", height=36,
                              fg_color="transparent", command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=8, pady=2)
            self.nav[key] = b
        ctx.show_tab = self.show
        self.show("generate")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.sidebar = sidebar
        self.usage_label = ctk.CTkLabel(sidebar, text="", wraplength=150, justify="left", anchor="w",
                                        font=ctk.CTkFont(size=11), text_color=("gray30", "gray70"))
        self.usage_label.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        ctx.usage.listeners.append(lambda: ctx.bus.post(self._refresh_usage))
        self.after(200, self._set_icon)  # CTk menimpa ikon di Windows jika dipasang terlalu awal
        self.after(600, self._startup_checks)

    def _refresh_usage(self) -> None:
        self.usage_label.configure(text=self.ctx.usage.summary(self.ctx.settings.language))

    def _set_icon(self) -> None:
        if os.name != "nt":
            return
        try:
            self.iconbitmap(str(resource_path("assets/icon.ico")))
        except Exception:  # noqa: BLE001 — ikon hanya kosmetik
            log.warning("ikon tidak bisa dimuat", exc_info=True)

    def _startup_checks(self) -> None:
        ctx, s = self.ctx, self.ctx.settings
        if getattr(s, "secrets_lost", False):
            messagebox.showinfo(ctx.tr("info.title"), ctx.tr("set.secrets_lost"))
        if not s.onboarded:
            if all_ready(check_steps(s, ctx.project)):
                s.onboarded = True  # sudah siap sejak awal: tidak perlu panduan
                s.save()
            else:
                from .ui.wizard import Wizard
                Wizard(self, ctx)
        if s.check_updates and s.update_url:
            ctx.bus.run(lambda: check_update(s.update_url, __version__), self._show_update,
                        lambda e: log.info("cek pembaruan gagal: %s", e))

    def _show_update(self, info) -> None:
        if info is None:
            return
        ctx = self.ctx
        box = ctk.CTkFrame(self.sidebar, fg_color="#1f6f43")
        box.pack(side="bottom", fill="x", padx=8, pady=10)
        self.update_status = ctk.CTkLabel(box, text=ctx.tr("set.update_found", v=info.version), wraplength=140)
        self.update_status.pack(padx=6, pady=(6, 2))
        if info.asset_url and can_self_update():
            self.update_btn = ctk.CTkButton(box, text=ctx.tr("update.now"), height=26, command=lambda: self._do_update(info))
        else:  # versi python / tanpa installer di rilis: buka halaman rilis
            self.update_btn = ctk.CTkButton(box, text=ctx.tr("set.update_open"), height=26, command=lambda: webbrowser.open(info.url))
        self.update_btn.pack(padx=6, pady=(0, 6))

    def _do_update(self, info) -> None:
        """Unduh installer (host & nama dibatasi, checksum diverifikasi), pasang senyap, lalu tutup aplikasi."""
        ctx = self.ctx
        if not messagebox.askyesno(ctx.tr("info.title"), ctx.tr("update.confirm", v=info.version)):
            return
        self.update_btn.configure(state="disabled")
        dest = Path(tempfile.gettempdir()) / "VibeMotionNext-update"

        def progress(done: int, total: int) -> None:
            pct = int(done * 100 / total) if total else 0
            ctx.bus.post(self.update_status.configure, text=ctx.tr("update.downloading", pct=pct))

        def ok(result) -> None:
            path, verified = result
            if not verified and not messagebox.askyesno(ctx.tr("info.title"), ctx.tr("update.unverified")):
                self.update_btn.configure(state="normal")
                return
            self.update_status.configure(text=ctx.tr("update.verified") if verified else "…")
            try:
                launch_installer(path)
            except Exception as e:  # noqa: BLE001
                self.update_btn.configure(state="normal")
                show_error(ctx, e)
                return
            self.on_close()  # installer menutup/menimpa aplikasi ini

        def err(e: Exception) -> None:
            log.error("update gagal: %s", e)
            self.update_btn.configure(state="normal")
            self.update_status.configure(text=ctx.tr("set.update_found", v=info.version))
            messagebox.showwarning(ctx.tr("info.title"), f"{ctx.tr('update.failed')}\n{e}")

        ctx.bus.run(lambda: download_installer(info, dest, on_progress=progress), ok, err)

    def show(self, key: str) -> None:
        if key != "editor":
            self.editor.commit()
        for k, frame in self.tabs.items():
            frame.pack_forget()
            self.nav[k].configure(fg_color=("#3b82f6" if k == key else "transparent"))
        self.tabs[key].pack(fill="both", expand=True)

    def report_callback_exception(self, exc, val, tb) -> None:
        """Error tak tertangani di callback Tk: catat ke log dan tampilkan pesan ramah (aplikasi tetap hidup)."""
        log.critical("Tk callback exception", exc_info=(exc, val, tb))
        try:
            show_error(self.ctx, val)
        except Exception:  # noqa: BLE001
            pass

    def on_close(self) -> None:
        for step in (self.ctx.flush, self.ctx.settings.save, self.tabs["run"].shutdown):
            try:  # tiap langkah dicoba terpisah supaya satu kegagalan tidak menahan jendela tertutup
                step()
            except Exception:  # noqa: BLE001
                log.exception("error saat menutup: %s", getattr(step, "__name__", step))
        self.destroy()


def selftest() -> int:
    """Pemeriksaan asap untuk build terbungkus: jendela + semua tab bisa dibuat dan dibuka. Kode keluar 0 = lolos."""
    setup_logging()
    result = log_dir() / "selftest.txt"
    try:
        app = App()
        for key in app.tabs:
            app.show(key)
            for _ in range(5):
                app.update()
        assert set(app.tabs) == {"generate", "editor", "run", "settings"}, "tab tidak lengkap"
        # modul yang diimpor lazy harus ikut terbungkus
        import vibemotion.ai.connection, vibemotion.ui.wizard  # noqa: F401, E401
        app.destroy()
        result.write_text(f"OK v{__version__}\n", encoding="utf-8")
        return 0
    except Exception as e:  # noqa: BLE001
        log.critical("selftest gagal", exc_info=True)
        result.write_text(f"GAGAL: {type(e).__name__}: {e}\n", encoding="utf-8")
        return 1


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    setup_logging()
    try:
        App().mainloop()
    except Exception:  # noqa: BLE001 — gagal saat start: tampilkan lokasi log
        log.critical("startup failed", exc_info=True)
        try:
            from tkinter import messagebox
            messagebox.showerror(APP_TITLE, f"Aplikasi gagal dimulai.\nLog: {log_dir() / 'app.log'}")
        except Exception:  # noqa: BLE001
            pass
        raise
