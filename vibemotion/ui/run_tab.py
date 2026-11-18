from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..context import AppContext
from .dialogs import show_error
from ..core import env_setup
from ..core.preview import PreviewServer
from ..core.render import FORMATS, RenderOptions, RenderQueue
from .widgets import LogBox


class RunTab(ctk.CTkFrame):
    def __init__(self, master, ctx: AppContext, editor):
        super().__init__(master, fg_color="transparent")
        self.ctx, self.editor = ctx, editor
        self.queue: RenderQueue | None = None
        s = ctx.settings
        ctx.log = self.log
        ctx.actions["setup_env"] = self.setup
        ctx.actions["render_ids"] = self.render_ids

        top = ctk.CTkFrame(self)
        top.pack(fill="x")
        ctk.CTkButton(top, text=ctx.tr("run.setup"), command=self.setup).pack(side="left", padx=6, pady=6)
        self.start_btn = ctk.CTkButton(top, text=ctx.tr("run.start"), command=self.start_preview)
        self.start_btn.pack(side="left", padx=6)
        ctk.CTkButton(top, text=ctx.tr("run.stop"), fg_color="gray40", width=80, command=self.stop_preview).pack(side="left")
        ctk.CTkButton(top, text=ctx.tr("run.open"), fg_color="gray40", command=self.open_browser).pack(side="left", padx=6)
        self.status = ctk.CTkLabel(top, text=ctx.tr("run.status_off"))
        self.status.pack(side="left", padx=10)
        self.autofix = ctk.CTkCheckBox(top, text=ctx.tr("run.autofix"))
        self.autofix.pack(side="right", padx=8)

        self.err_bar = ctk.CTkFrame(self, fg_color="#7a1f1f")
        self.err_label = ctk.CTkLabel(self.err_bar, text=ctx.tr("run.error"))
        self.err_label.pack(side="left", padx=8, pady=4)
        ctk.CTkButton(self.err_bar, text=ctx.tr("run.fix"), width=140,
                      command=self.fix_now).pack(side="right", padx=6, pady=4)

        rend = ctk.CTkFrame(self)
        rend.pack(fill="x", pady=8)
        self.fmt = ctk.CTkOptionMenu(rend, values=list(FORMATS), width=90)
        self.fmt.set(s.render_format)
        self.hw = ctk.CTkOptionMenu(rend, values=["disable", "if-possible", "required"], width=120)
        self.hw.set(s.hardware_acceleration)
        self.quality = ctk.CTkOptionMenu(rend, values=["100%", "50% (draft)", "25% (draft)"], width=120)
        self.quality.set("100%")
        self.conc = ctk.CTkEntry(rend, width=60)
        self.conc.insert(0, str(s.concurrency))
        for label, w in (("run.format", self.fmt), ("run.quality", self.quality), ("run.hw", self.hw),
                         ("run.conc", self.conc)):
            ctk.CTkLabel(rend, text=ctx.tr(label)).pack(side="left", padx=(10, 2))
            w.pack(side="left")
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x")
        ctk.CTkButton(row2, text=ctx.tr("run.export"), width=130, fg_color="gray40",
                      command=self.pick_export).pack(side="left")
        self.export_label = ctk.CTkLabel(row2, text=s.export_dir, anchor="w")
        self.export_label.pack(side="left", padx=8)
        self.render_btn = ctk.CTkButton(row2, text=ctx.tr("run.render"), command=lambda: self.render(False))
        self.render_all_btn = ctk.CTkButton(row2, text=ctx.tr("run.render_all"), command=lambda: self.render(True))
        self.cancel_btn = ctk.CTkButton(row2, text=ctx.tr("run.cancel"), fg_color="#a33", width=80, command=self.cancel)
        self.cancel_btn.pack(side="right", padx=4)
        self.render_all_btn.pack(side="right", padx=4)
        self.render_btn.pack(side="right", padx=4)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(fill="x", pady=6)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # ---------- util ----------
    def log(self, line: str) -> None:
        self.logbox.append(line)

    def _need_env(self) -> bool:
        if env_setup.is_installed(self.ctx.project):
            return True
        messagebox.showinfo(self.ctx.tr("info.title"), self.ctx.tr("run.setup"))
        return False

    # ---------- setup & preview ----------
    def setup(self) -> None:
        bus, ctx = self.ctx.bus, self.ctx
        ctx.flush()

        def err(e):
            self.log(f"✖ {e}")
            show_error(ctx, e)

        bus.run(lambda: env_setup.setup_environment(ctx.project, lambda l: bus.post(self.log, l)),
                lambda _r: self.log("✔ OK"), err)

    def _on_compile_error(self, text: str) -> None:
        self.ctx.last_error = text
        self.err_bar.pack(fill="x", pady=(6, 0), before=self.logbox)
        if self.autofix.get() and self.ctx.autofix_attempts < 2:
            self.ctx.autofix_attempts += 1
            self.fix_now()

    def fix_now(self) -> None:
        self.editor.auto_fix(self.ctx.last_error)
        self.ctx.show_tab("editor")

    def start_preview(self) -> None:
        if not self._need_env():
            return
        self.ctx.flush()
        self.err_bar.pack_forget()
        if self.ctx.preview is None or not self.ctx.preview.running:
            bus = self.ctx.bus
            self.ctx.preview = PreviewServer(
                self.ctx.project.root, lambda l: bus.post(self.log, l),
                lambda t: bus.post(self._on_compile_error, t))
        pv = self.ctx.preview
        self.status.configure(text="…")

        def ok(url):
            self.status.configure(text=f"{self.ctx.tr('run.status_on')} — {url}")
            self.open_browser()

        def err(e):
            self.status.configure(text=self.ctx.tr("run.status_off"))
            show_error(self.ctx, e)

        self.ctx.bus.run(pv.start, ok, err)

    def stop_preview(self) -> None:
        if self.ctx.preview:
            self.ctx.preview.stop()
        self.err_bar.pack_forget()
        self.status.configure(text=self.ctx.tr("run.status_off"))

    def open_browser(self) -> None:
        pv = self.ctx.preview
        if pv and pv.url:
            webbrowser.open(f"{pv.url}/{self.ctx.selected.comp_id}")

    # ---------- render ----------
    def pick_export(self) -> None:
        d = filedialog.askdirectory()
        if d:
            self.ctx.settings.export_dir = d
            self.export_label.configure(text=d)
            self.ctx.settings.save()

    def render(self, everything: bool) -> None:
        self.ctx.flush()
        self.render_ids([i.id for i in self.ctx.project.items] if everything else [self.ctx.selected_id])

    def render_ids(self, ids: list[str]) -> None:
        """Render daftar video tertentu (dipakai juga oleh dialog varian rasio)."""
        if not self._need_env():
            return
        if self.queue and self.queue.busy:
            return
        s, bus = self.ctx.settings, self.ctx.bus
        try:
            conc = max(0, int(self.conc.get() or 0))
        except ValueError:
            conc = 0
        s.render_format, s.hardware_acceleration, s.concurrency = self.fmt.get(), self.hw.get(), conc
        s.save()
        self.ctx.flush()
        total = len(ids)
        done = {"n": 0}

        def on_done(vid, out, err):
            done["n"] += 1
            name = self.ctx.project.get(vid).name
            bus.post(self.log, f"✔ {name} → {out}" if out else f"✖ {name}: {err}")
            if done["n"] >= total:
                bus.post(lambda: self.render_btn.configure(state="normal"))
                bus.post(lambda: self.render_all_btn.configure(state="normal"))

        self.queue = RenderQueue(
            self.ctx.project, Path(s.export_dir),
            RenderOptions(fmt=s.render_format, concurrency=conc, hardware_acceleration=s.hardware_acceleration,
                          scale=float(self.quality.get().split("%")[0]) / 100),
            on_log=lambda l: bus.post(self.log, l),
            on_progress=lambda vid, p: bus.post(self.progress.set, (done["n"] + p) / total),
            on_done=on_done)
        self.progress.set(0)
        self.render_btn.configure(state="disabled")
        self.render_all_btn.configure(state="disabled")
        self.queue.start(ids)

    def cancel(self) -> None:
        if self.queue:
            self.queue.cancel()
            self.render_btn.configure(state="normal")
            self.render_all_btn.configure(state="normal")

    def shutdown(self) -> None:
        if self.queue:
            self.queue.cancel()
        self.stop_preview()
