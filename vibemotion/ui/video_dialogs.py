"""Dialog khusus video: varian rasio dan audio (musik latar + voice-over)."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..ai.pipeline import make_ratio_variants
from ..config import RATIOS
from ..context import AppContext
from .dialogs import show_error

AUDIO_TYPES = [("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac"), ("All", "*.*")]


class RatioDialog(ctk.CTkToplevel):
    def __init__(self, master, ctx: AppContext, editor):
        super().__init__(master)
        self.ctx, self.editor = ctx, editor
        self.src = ctx.selected
        self.title(ctx.tr("rat.title"))
        self.geometry("460x470")
        self.lift()
        ctk.CTkLabel(self, text=f"{self.src.name}  ({self.src.width}×{self.src.height})",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(self, text=ctx.tr("rat.pick"), anchor="w").pack(anchor="w", padx=18, pady=(0, 6))
        self.boxes: dict[str, ctk.CTkCheckBox] = {}
        for label, (w, h) in RATIOS.items():
            box = ctk.CTkCheckBox(self, text=f"{label}   ({w}×{h})")
            box.pack(anchor="w", padx=28, pady=2)
            if (w, h) == (self.src.width, self.src.height):
                box.configure(state="disabled")  # ukuran sumber: tidak perlu varian
            self.boxes[label] = box
        for label in ("9:16", "1:1"):  # pilihan umum terpilih awal
            if self.boxes[label].cget("state") != "disabled":
                self.boxes[label].select()
        self.adapt = ctk.CTkCheckBox(self, text=ctx.tr("rat.adapt"))
        self.adapt.pack(anchor="w", padx=18, pady=(14, 4))
        self.status = ctk.CTkLabel(self, text="", anchor="w", wraplength=420, justify="left")
        self.status.pack(fill="x", padx=18, pady=4)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=18, pady=14)
        self.btn_create = ctk.CTkButton(row, text=ctx.tr("rat.create"), width=150, command=lambda: self.create(False))
        self.btn_create.pack(side="left")
        self.btn_render = ctk.CTkButton(row, text=ctx.tr("rat.create_render"), width=190, fg_color="#2a7",
                                        command=lambda: self.create(True))
        self.btn_render.pack(side="right")

    def chosen(self) -> dict[str, tuple[int, int]]:
        return {k: RATIOS[k] for k, b in self.boxes.items() if b.get() and b.cget("state") != "disabled"}

    def create(self, render: bool) -> None:
        ctx = self.ctx
        ratios = self.chosen()
        if not ratios:
            messagebox.showinfo(ctx.tr("info.title"), ctx.tr("rat.none"))
            return
        use_ai = bool(self.adapt.get())
        svc = self.editor._service() if use_ai else None
        if use_ai and svc is None:
            return
        self.editor.commit()
        ctx.project.save()
        for b in (self.btn_create, self.btn_render):
            b.configure(state="disabled")
        post = lambda t: ctx.bus.post(self.status.configure, text=t)

        def work():
            return make_ratio_variants(svc, ctx.project, self.src.id, ratios, adapt_with_ai=use_ai,
                                       auto_check=ctx.settings.auto_check, status=post)

        def ok(result):
            items, notes = result
            ctx.selected_id = items[0].id if items else self.src.id
            ctx.notify_videos_changed()
            msg = ctx.tr("rat.done", n=len(items)) + ("\n" + "\n".join(notes) if notes else "")
            self.editor.status.configure(text=ctx.tr("rat.done", n=len(items)))
            if notes:
                messagebox.showinfo(ctx.tr("info.title"), msg)
            self.destroy()
            if render and items:
                ctx.show_tab("run")
                action = ctx.actions.get("render_ids")
                if action:
                    action([self.src.id] + [i.id for i in items])

        def err(e):
            for b in (self.btn_create, self.btn_render):
                b.configure(state="normal")
            show_error(ctx, e)

        ctx.bus.run(work, ok, err)


class AudioDialog(ctk.CTkToplevel):
    def __init__(self, master, ctx: AppContext, editor):
        super().__init__(master)
        self.ctx, self.editor = ctx, editor
        self.item = ctx.selected
        self.music, self.voice = self.item.music, self.item.voiceover
        self.title(ctx.tr("aud.title"))
        self.geometry("520x400")
        self.lift()
        ctk.CTkLabel(self, text=self.item.name, font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=18, pady=(16, 6))
        self.music_label = self._row("aud.music", lambda: self.pick("music"), lambda: self.clear("music"))
        self.volume_label = ctk.CTkLabel(self, text="", anchor="w")
        self.volume_label.pack(anchor="w", padx=18, pady=(10, 0))
        self.slider = ctk.CTkSlider(self, from_=0, to=1, number_of_steps=20, command=self._on_volume)
        self.slider.set(self.item.music_volume)
        self.slider.pack(fill="x", padx=18, pady=(2, 8))
        self._on_volume(self.item.music_volume)
        self.voice_label = self._row("aud.voice", lambda: self.pick("voice"), lambda: self.clear("voice"))
        ctk.CTkLabel(self, text=ctx.tr("aud.hint"), wraplength=480, justify="left", anchor="w",
                     text_color=("gray30", "gray70")).pack(anchor="w", padx=18, pady=(14, 0))
        ctk.CTkButton(self, text=ctx.tr("aud.apply"), height=36, fg_color="#2a7", command=self.apply).pack(
            side="bottom", fill="x", padx=18, pady=14)
        self._refresh()

    def _row(self, key: str, pick, clear) -> ctk.CTkLabel:
        ctk.CTkLabel(self, text=self.ctx.tr(key), anchor="w").pack(anchor="w", padx=18, pady=(8, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18)
        label = ctk.CTkLabel(row, text="", anchor="w")
        label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text=self.ctx.tr("aud.clear"), width=70, fg_color="#a33", command=clear).pack(side="right")
        ctk.CTkButton(row, text=self.ctx.tr("aud.choose"), width=120, command=pick).pack(side="right", padx=6)
        return label

    def _refresh(self) -> None:
        none = self.ctx.tr("aud.none")
        self.music_label.configure(text=Path(self.music).name if self.music else none)
        self.voice_label.configure(text=Path(self.voice).name if self.voice else none)

    def _on_volume(self, value: float) -> None:
        self.volume_label.configure(text=f"{self.ctx.tr('aud.volume')}: {round(float(value) * 100)}%")

    def set_files(self, music: str | None = None, voice: str | None = None) -> None:
        if music is not None:
            self.music = music
        if voice is not None:
            self.voice = voice
        self._refresh()

    def pick(self, which: str) -> None:
        path = filedialog.askopenfilename(filetypes=AUDIO_TYPES)
        if not path:
            return
        try:
            ref = self.ctx.project.import_asset(Path(path))
        except Exception as e:  # noqa: BLE001
            show_error(self.ctx, e)
            return
        self.set_files(**{("music" if which == "music" else "voice"): ref})

    def clear(self, which: str) -> None:
        self.set_files(**{("music" if which == "music" else "voice"): ""})

    def apply(self) -> None:
        ctx = self.ctx
        ctx.project.set_audio(self.item.id, music=self.music, volume=self.slider.get(), voiceover=self.voice)
        self.editor.commit()
        ctx.project.save()  # menulis ulang Root.tsx dengan pembungkus <Audio>
        self.editor.status.configure(text=ctx.tr("aud.apply"))
        self.destroy()
