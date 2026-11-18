from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from ..ai.extras import edit_checked, transcribe
from ..ai.pipeline import make_validator, make_variations
from ..ai.prompts import GenerationSpec
from ..ai.service import AIService, make_provider
from ..config import RATIOS
from ..context import AppContext
from ..core import env_setup
from ..core.code_utils import parse_duration_to_seconds
from ..core.highlight import COLORS, tokenize
from ..core.library import UserTemplates
from ..core.portable import export_project, import_project
from ..core.validate import has_remotion_export
from ..core.presets import RENDER_PRESETS, apply_preset
from ..core.textsearch import find_all, next_match, replace_all
from ..core.thumbs import existing_thumb, make_thumbs
from .dialogs import show_error
from .video_dialogs import AudioDialog, RatioDialog
from .widgets import MONO, get_text, set_text

AUTOSAVE_MS = 15_000
HIGHLIGHT_DELAY_MS = 250


class EditorTab(ctk.CTkFrame):
    def __init__(self, master, ctx: AppContext):
        super().__init__(master, fg_color="transparent")
        self.ctx = ctx
        self.backup: str | None = None  # kode asli saat usulan AI sedang ditinjau
        self._loaded_id: str | None = None
        self._dirty = False
        self._hl_job = None
        self._img_cache: dict[Path, ctk.CTkImage] = {}

        self._build_sidebar()
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True)
        self._build_meta(main)
        self._build_banner(main)
        self._build_findbar(main)
        self._build_code(main)
        self._build_toolbar(main)
        self._build_chat(main)

        ctx.on_videos_changed(self.refresh)
        ctx.register_flusher(self.commit)
        self.refresh()
        self.after(AUTOSAVE_MS, self._autosave)

    # ================= susunan UI =================
    def _build_sidebar(self) -> None:
        ctx = self.ctx
        side = ctk.CTkFrame(self, width=260)
        side.pack(side="left", fill="y", padx=(0, 10))
        side.pack_propagate(False)
        ctk.CTkLabel(side, text=ctx.tr("ed.videos"), font=ctk.CTkFont(weight="bold")).pack(pady=(8, 2))
        self.list = ctk.CTkScrollableFrame(side)
        self.list.pack(fill="both", expand=True, padx=4)
        grid = ctk.CTkFrame(side, fg_color="transparent")
        grid.pack(fill="x", padx=4, pady=4)
        buttons = [("ed.add", self.add), ("ed.dup", self.duplicate), ("ed.del", self.delete), ("ed.merge", self.merge),
                   ("ed.thumbs", self.generate_thumbs), ("ed.export", self.export_zip), ("ed.import", self.import_zip)]
        for i, (key, cmd) in enumerate(buttons):
            ctk.CTkButton(grid, text=ctx.tr(key), height=28, command=cmd).grid(
                row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(grid, text="↑", width=40, height=28, command=lambda: self.move(-1)).grid(row=4, column=0, padx=2, pady=2, sticky="ew")
        ctk.CTkButton(grid, text="↓", width=40, height=28, command=lambda: self.move(1)).grid(row=4, column=1, padx=2, pady=2, sticky="ew")
        grid.grid_columnconfigure((0, 1), weight=1)

    def _build_meta(self, main) -> None:
        ctx = self.ctx
        meta = ctk.CTkFrame(main, fg_color="transparent")
        meta.pack(fill="x")

        def column(label_key: str, factory):
            col = ctk.CTkFrame(meta, fg_color="transparent")
            col.pack(side="left", padx=3)
            ctk.CTkLabel(col, text=ctx.tr(label_key), anchor="w", font=ctk.CTkFont(size=11),
                         text_color=("gray30", "gray70")).pack(fill="x")
            w = factory(col)
            w.pack()
            return w

        self.name = column("ed.name", lambda f: ctk.CTkEntry(f, width=170))
        self.fps = column("ed.fps", lambda f: ctk.CTkEntry(f, width=60))
        self.dur = column("ed.dur", lambda f: ctk.CTkEntry(f, width=80))
        apply_col = ctk.CTkFrame(meta, fg_color="transparent")
        apply_col.pack(side="left", padx=3)
        ctk.CTkLabel(apply_col, text=" ", font=ctk.CTkFont(size=11)).pack()
        ctk.CTkButton(apply_col, text=ctx.tr("ed.apply_meta"), width=80, command=self.apply_meta).pack()
        self.size_map = {f"{r}  ({w}×{h})": (w, h) for r, (w, h) in RATIOS.items()}
        self.size = column("ed.size", lambda f: ctk.CTkOptionMenu(
            f, values=list(self.size_map), width=160, command=lambda _v: self.apply_meta()))
        self.preset = column("ed.preset", lambda f: ctk.CTkOptionMenu(
            f, values=list(RENDER_PRESETS), width=200, command=self.use_preset))
        self.preset.set(ctx.tr("ed.preset_ph"))
        ctk.CTkButton(meta, text=ctx.tr("ed.assets"), width=120, fg_color="gray40",
                      command=self.import_assets).pack(side="right")

    def _build_banner(self, main) -> None:
        ctx = self.ctx
        self.banner = ctk.CTkFrame(main, fg_color="#7a5b00")
        ctk.CTkLabel(self.banner, text=ctx.tr("ed.pending")).pack(side="left", padx=8, pady=4)
        ctk.CTkButton(self.banner, text=ctx.tr("ed.reject"), width=90, fg_color="#a33",
                      command=self.reject).pack(side="right", padx=4, pady=4)
        ctk.CTkButton(self.banner, text=ctx.tr("ed.approve"), width=90, fg_color="#2a7",
                      command=self.approve).pack(side="right", padx=4)

    def _build_findbar(self, main) -> None:
        ctx = self.ctx
        self.findbar = ctk.CTkFrame(main)
        self.find_entry = ctk.CTkEntry(self.findbar, width=200, placeholder_text=ctx.tr("ed.find_ph"))
        self.repl_entry = ctk.CTkEntry(self.findbar, width=200, placeholder_text=ctx.tr("ed.repl_ph"))
        self.case_box = ctk.CTkCheckBox(self.findbar, text=ctx.tr("ed.case"), width=50, command=self._update_count)
        self.regex_box = ctk.CTkCheckBox(self.findbar, text=ctx.tr("ed.regex"), width=50, command=self._update_count)
        self.find_info = ctk.CTkLabel(self.findbar, text="", width=110, anchor="w")
        self.find_entry.pack(side="left", padx=4, pady=4)
        ctk.CTkButton(self.findbar, text="◀", width=30, command=lambda: self.find_next(False)).pack(side="left")
        ctk.CTkButton(self.findbar, text="▶", width=30, command=lambda: self.find_next(True)).pack(side="left", padx=2)
        self.repl_entry.pack(side="left", padx=4)
        ctk.CTkButton(self.findbar, text=ctx.tr("ed.replace"), width=70, command=self.replace_one).pack(side="left")
        ctk.CTkButton(self.findbar, text=ctx.tr("ed.replace_all"), width=100, command=self.replace_everything).pack(side="left", padx=4)
        self.case_box.pack(side="left", padx=2)
        self.regex_box.pack(side="left", padx=2)
        self.find_info.pack(side="left", padx=4)
        ctk.CTkButton(self.findbar, text="✕", width=28, fg_color="gray40", command=self.toggle_find).pack(side="right", padx=4)
        self.find_entry.bind("<Return>", lambda _e: self.find_next(True))
        self.find_entry.bind("<KeyRelease>", lambda _e: self._update_count())

    def _build_code(self, main) -> None:
        self.code = ctk.CTkTextbox(main, font=MONO, wrap="none", undo=True)
        self.code.pack(fill="both", expand=True, pady=6)
        tb = self.code._textbox
        for kind, color in COLORS.items():
            tb.tag_config(kind, foreground=color)
        tb.tag_config("found", background="#b58900", foreground="#000000")
        tb.tag_raise("found")
        self.code.bind("<KeyRelease>", self._on_key)
        for seq, fn in (("<Control-s>", self.save), ("<Control-f>", self.toggle_find), ("<Control-h>", self.open_history)):
            self.code.bind(seq, lambda _e, f=fn: (f(), "break")[1])

    def _build_toolbar(self, main) -> None:
        ctx = self.ctx
        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.pack(fill="x")
        ctk.CTkButton(bar, text=ctx.tr("ed.save"), width=100, command=self.save).pack(side="left")
        ctk.CTkButton(bar, text=ctx.tr("ed.history"), width=100, fg_color="gray40",
                      command=self.open_history).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=ctx.tr("ed.find"), width=90, fg_color="gray40",
                      command=self.toggle_find).pack(side="left")
        ctk.CTkButton(bar, text=ctx.tr("ed.heal"), width=120, fg_color="#6b46c1",
                      command=self.auto_fix).pack(side="left", padx=4)
        ctk.CTkButton(bar, text=ctx.tr("ed.transcribe"), width=130, fg_color="gray40",
                      command=self.transcribe_media).pack(side="left")
        self.status = ctk.CTkLabel(bar, text="", anchor="w")
        self.status.pack(side="left", padx=8)
        bar2 = ctk.CTkFrame(main, fg_color="transparent")
        bar2.pack(fill="x", pady=(6, 0))
        for key, cmd in (("ed.audio", self.open_audio), ("ed.ratios", self.open_ratios),
                         ("ed.save_tpl", self.save_template), ("ed.variations", self.make_variations_bg)):
            ctk.CTkButton(bar2, text=ctx.tr(key), width=150, fg_color="gray40", command=cmd).pack(side="left", padx=(0, 4))
        chips = ctk.CTkFrame(main, fg_color="transparent")
        chips.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(chips, text=ctx.tr("ed.fb_title"), font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        for key in ("faster", "slower", "bright", "bigger", "simpler", "dramatic"):
            ctk.CTkButton(chips, text=ctx.tr(f"fb.{key}"), height=26, width=70, fg_color=("gray75", "gray30"),
                          text_color=("black", "white"), command=lambda k=key: self.quick_feedback(k)).pack(side="left", padx=2)

    def _build_chat(self, main) -> None:
        ctx = self.ctx
        chat = ctk.CTkFrame(main, fg_color="transparent")
        chat.pack(fill="x", pady=(6, 0))
        self.ask = ctk.CTkEntry(chat, placeholder_text=ctx.tr("ed.ask"))
        self.ask.pack(side="left", fill="x", expand=True)
        self.ask.bind("<Return>", lambda _e: self.send())
        self.send_btn = ctk.CTkButton(chat, text=ctx.tr("ed.send"), width=90, command=self.send)
        self.send_btn.pack(side="left", padx=(6, 0))

    # ================= daftar video (+ thumbnail) =================
    def _thumb_image(self, item) -> ctk.CTkImage | None:
        path = existing_thumb(self.ctx.project, item)
        if path is None:
            return None
        if path not in self._img_cache:
            try:
                im = Image.open(path)
                im.load()
                w, h = im.size
                r = min(78 / w, 50 / h)
                self._img_cache[path] = ctk.CTkImage(im, size=(max(1, int(w * r)), max(1, int(h * r))))
            except Exception:  # noqa: BLE001 — gambar rusak: tampilkan tanpa thumbnail
                return None
        return self._img_cache[path]

    def refresh(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        for it in self.ctx.project.items:
            active = it.id == self.ctx.selected_id
            row = ctk.CTkFrame(self.list, fg_color=("#3b82f6" if active else "transparent"), corner_radius=6)
            row.pack(fill="x", pady=1)
            img = self._thumb_image(it)
            pic = ctk.CTkLabel(row, text="" if img else "▶", image=img, width=78, height=50)
            pic.pack(side="left", padx=4, pady=3)
            label = ctk.CTkLabel(row, text=it.name, anchor="w", justify="left", wraplength=120,
                                 text_color=("white" if active else None))
            label.pack(side="left", fill="x", expand=True, padx=2)
            for w in (row, pic, label):
                w.bind("<Button-1>", lambda _e, i=it.id: self.select(i))
        self.load_selected(force=True)

    def select(self, video_id: str) -> None:
        if video_id == self.ctx.selected_id:
            return
        self.commit()
        self.ctx.selected_id = video_id
        self.refresh()

    def set_code(self, text: str) -> None:
        """Isi editor + highlight; tidak dianggap perubahan pengguna."""
        yview = self.code._textbox.yview()[0]
        set_text(self.code, text)
        self.code._textbox.yview_moveto(yview)
        self._dirty = False
        self._apply_highlight()

    def load_selected(self, force: bool = False) -> None:
        it = self.ctx.selected
        if not force and self._loaded_id == it.id:
            return
        switched = self._loaded_id != it.id
        self._loaded_id = it.id
        self.backup = None
        self.banner.pack_forget()
        self.set_code(it.code)
        if switched:
            self.code._textbox.yview_moveto(0)
        for w, v in ((self.name, it.name), (self.fps, str(it.fps)), (self.dur, f"{it.duration_sec:g}")):
            w.delete(0, "end")
            w.insert(0, v)
        label = next((k for k, v in self.size_map.items() if v == (it.width, it.height)), None)
        if label is None:  # ukuran khusus: tampilkan apa adanya
            label = f"custom  ({it.width}×{it.height})"
            self.size_map[label] = (it.width, it.height)
            self.size.configure(values=list(self.size_map))
        self.size.set(label)

    # ================= penyimpanan, riwayat, autosave =================
    def commit(self) -> None:
        """Salin isi editor ke model (tidak menulis disk)."""
        if self._loaded_id is None or self.backup is not None:
            return
        try:
            self.ctx.project.get(self._loaded_id).code = get_text(self.code)
        except KeyError:
            pass

    def save(self) -> None:
        self.commit()
        self.ctx.autofix_attempts = 0
        self.ctx.project.save()
        if self._loaded_id:
            self.ctx.project.snapshot(self._loaded_id, "manual")
        self._dirty = False
        code = get_text(self.code)
        warn = not has_remotion_export(code)
        self.status.configure(text=self.ctx.tr("ed.save_warn_export") if warn else self.ctx.tr("ed.saved"),
                              text_color="#e5a50a" if warn else ("gray10", "gray90"))

    def _on_key(self, event=None) -> None:
        # Ctrl+S / Ctrl+F / Ctrl+H bukan perubahan isi
        if event is not None and (event.state & 0x4) and str(event.keysym).lower() in ("s", "f", "h", "control_l", "control_r"):
            return
        self._dirty = True
        if self._hl_job:
            self.after_cancel(self._hl_job)
        self._hl_job = self.after(HIGHLIGHT_DELAY_MS, self._apply_highlight)

    def _autosave(self) -> None:
        try:
            if self._dirty and self.backup is None:
                self.commit()
                self.ctx.project.save()  # tanpa snapshot: riwayat hanya untuk simpan manual/AI
                self._dirty = False
                self.status.configure(text=self.ctx.tr("ed.autosaved"))
        except Exception:  # noqa: BLE001 — autosave tidak boleh mengganggu pengguna
            pass
        self.after(AUTOSAVE_MS, self._autosave)

    def open_history(self) -> None:
        ctx = self.ctx
        if self.backup is not None or self._loaded_id is None:
            return
        self.commit()
        vid = self._loaded_id
        ctx.project.snapshot(vid, "saat-dibuka")  # kondisi sekarang selalu bisa dikembalikan
        entries = ctx.project.history.list(vid)
        dlg = ctk.CTkToplevel(self)
        dlg.title(ctx.tr("ed.hist_title"))
        dlg.geometry("980x580")
        dlg.lift()
        listing = ctk.CTkScrollableFrame(dlg, width=270)
        listing.pack(side="left", fill="y", padx=8, pady=8)
        right = ctk.CTkFrame(dlg, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        preview = ctk.CTkTextbox(right, font=MONO, wrap="none")
        preview.pack(fill="both", expand=True)
        preview.configure(state="disabled")
        chosen: dict[str, str | None] = {"id": None}

        def show(entry) -> None:
            chosen["id"] = entry.id
            preview.configure(state="normal")
            set_text(preview, ctx.project.history.read(vid, entry.id))
            preview.configure(state="disabled")

        def restore() -> None:
            if not chosen["id"]:
                return
            text = ctx.project.history.read(vid, chosen["id"])
            ctx.project.snapshot(vid, "sebelum-pulih")
            ctx.project.get(vid).code = text
            self.set_code(text)
            ctx.project.save()
            ctx.project.snapshot(vid, "dipulihkan")
            dlg.destroy()
            self.status.configure(text=ctx.tr("ed.restored"))

        if not entries:
            ctk.CTkLabel(listing, text=ctx.tr("ed.hist_empty")).pack(pady=10)
        for e in entries:
            ctk.CTkButton(listing, text=f"{e.when}  ·  {e.label}\n{e.size} B", anchor="w", height=42,
                          fg_color="transparent", border_width=1, command=lambda en=e: show(en)).pack(fill="x", pady=2)
        ctk.CTkButton(right, text=ctx.tr("ed.hist_restore"), height=36, fg_color="#2a7", command=restore).pack(fill="x", pady=(8, 0))
        if entries:
            show(entries[0])

    # ================= highlight =================
    def _apply_highlight(self) -> None:
        self._hl_job = None
        tb = self.code._textbox
        for kind in COLORS:
            tb.tag_remove(kind, "1.0", "end")
        for kind, start, end in tokenize(get_text(self.code)):
            tb.tag_add(kind, f"1.0+{start}c", f"1.0+{end}c")

    # ================= cari / ganti =================
    def toggle_find(self) -> None:
        if self.findbar.winfo_ismapped():
            self.findbar.pack_forget()
            self.code._textbox.tag_remove("found", "1.0", "end")
            self.code.focus_set()
            return
        self.findbar.pack(fill="x", before=self.code, pady=(4, 0))
        self.find_entry.focus_set()
        self._update_count()

    def _spans(self) -> list[tuple[int, int]]:
        try:
            return find_all(get_text(self.code), self.find_entry.get(), bool(self.case_box.get()), bool(self.regex_box.get()))
        except ValueError as e:
            self.find_info.configure(text=str(e)[:40])
            return []

    def _update_count(self) -> None:
        if self.find_entry.get():
            self.find_info.configure(text=self.ctx.tr("ed.found", n=len(self._spans())))
        else:
            self.find_info.configure(text="")

    def find_next(self, forward: bool = True) -> None:
        tb = self.code._textbox
        spans = self._spans()
        pos = len(tb.get("1.0", "insert"))
        idx = next_match(spans, pos, forward)
        tb.tag_remove("found", "1.0", "end")
        if idx is None:
            self._update_count()
            return
        start, end = spans[idx]
        tb.tag_add("found", f"1.0+{start}c", f"1.0+{end}c")
        tb.mark_set("insert", f"1.0+{end if forward else start}c")
        tb.see(f"1.0+{start}c")
        self.find_info.configure(text=f"{idx + 1}/{len(spans)}")

    def replace_one(self) -> None:
        tb = self.code._textbox
        ranges = tb.tag_ranges("found")
        if ranges:
            a, b = str(ranges[0]), str(ranges[1])
            current = tb.get(a, b)
            spans = find_all(current, self.find_entry.get(), bool(self.case_box.get()), bool(self.regex_box.get()))
            if spans and spans[0] == (0, len(current)):  # yang tersorot memang cocok
                new, _n = replace_all(current, self.find_entry.get(), self.repl_entry.get(),
                                      bool(self.case_box.get()), bool(self.regex_box.get()))
                tb.delete(a, b)
                tb.insert(a, new)
                tb.mark_set("insert", f"{a}+{len(new)}c")
                self._on_key()
        self.find_next(True)

    def replace_everything(self) -> None:
        try:
            new, count = replace_all(get_text(self.code), self.find_entry.get(), self.repl_entry.get(),
                                     bool(self.case_box.get()), bool(self.regex_box.get()))
        except ValueError as e:
            self.find_info.configure(text=str(e)[:40])
            return
        if count:
            self.set_code(new)
            self._dirty = True
        self.find_info.configure(text=self.ctx.tr("ed.replaced", n=count))

    # ================= metadata & preset =================
    def apply_meta(self) -> None:
        it = self.ctx.selected
        it.name = self.name.get().strip() or it.name
        try:
            it.fps = max(1, min(120, int(self.fps.get())))
        except ValueError:
            pass
        it.duration_sec = parse_duration_to_seconds(self.dur.get(), it.duration_sec)
        it.width, it.height = self.size_map.get(self.size.get(), (it.width, it.height))
        self.commit()
        self.ctx.project.save()
        self.refresh()

    def use_preset(self, key: str) -> None:
        apply_preset(self.ctx.selected, key)
        self.preset.set(self.ctx.tr("ed.preset_ph"))
        self.commit()
        self.ctx.project.save()
        self.refresh()

    # ================= operasi daftar =================
    def add(self) -> None:
        self.commit()
        s = self.ctx.settings
        self.ctx.selected_id = self.ctx.project.add(fps=s.fps, duration_sec=s.duration_sec).id
        self.ctx.project.save()
        self.ctx.notify_videos_changed()

    def duplicate(self) -> None:
        self.commit()
        self.ctx.selected_id = self.ctx.project.duplicate(self.ctx.selected_id).id
        self.ctx.project.save()
        self.ctx.notify_videos_changed()

    def delete(self) -> None:
        if len(self.ctx.project.items) <= 1:
            return
        if messagebox.askyesno(self.ctx.tr("ed.del"), f"{self.ctx.selected.name}?"):
            self.ctx.project.snapshot(self.ctx.selected_id, "sebelum-hapus")
            self.ctx.project.remove(self.ctx.selected_id)
            self._loaded_id = None
            self.ctx.project.save()
            self.ctx.notify_videos_changed()

    def move(self, delta: int) -> None:
        self.commit()
        self.ctx.project.move(self.ctx.selected_id, delta)
        self.ctx.project.save()
        self.refresh()

    def merge(self) -> None:
        self.commit()
        try:
            item = self.ctx.project.merge([i.id for i in self.ctx.project.items])
        except ValueError as e:
            messagebox.showinfo(self.ctx.tr("info.title"), str(e))
            return
        self.ctx.selected_id = item.id
        self.ctx.project.save()
        self.ctx.notify_videos_changed()

    def import_assets(self) -> None:
        files = filedialog.askopenfilenames()
        for f in files:
            self.ctx.project.import_asset(Path(f))
        if files:
            self.status.configure(text=", ".join(self.ctx.project.list_assets()[-3:]))

    # ================= audio, varian, template, umpan balik =================
    def open_audio(self) -> None:
        self.commit()
        AudioDialog(self, self.ctx, self)

    def open_ratios(self) -> None:
        self.commit()
        RatioDialog(self, self.ctx, self)

    def quick_feedback(self, key: str) -> None:
        if self.backup is not None:
            return
        self.ask.delete(0, "end")
        self.ask.insert(0, self.ctx.tr(f"fb.{key}_req"))
        self.send()

    def save_template(self) -> None:
        dlg = ctk.CTkInputDialog(text=self.ctx.tr("ed.tpl_name"), title=self.ctx.tr("ed.save_tpl"))
        name = dlg.get_input()
        if name and name.strip():
            self.save_template_as(name)

    def save_template_as(self, name: str) -> None:
        ctx = self.ctx
        self.commit()
        it = ctx.selected
        try:
            tpl = UserTemplates().save(name, it.code, it.duration_sec)
        except ValueError as e:
            show_error(ctx, e)
            return
        reload = ctx.actions.get("reload_templates")
        if reload:
            reload()
        self.status.configure(text=ctx.tr("ed.template_saved", name=tpl.name))

    def make_variations_bg(self) -> None:
        ctx = self.ctx
        svc = self._service()
        if not svc or self.backup is not None:
            return
        self.commit()
        ctx.project.save()
        vid, auto = ctx.selected_id, ctx.settings.auto_check
        post = lambda t: ctx.bus.post(self.status.configure, text=t)

        def ok(result):
            items, notes = result
            self.status.configure(text=ctx.tr("ed.variations_done", n=len(items)))
            if items:
                ctx.selected_id = items[0].id
            ctx.notify_videos_changed()
            if notes:
                messagebox.showinfo(ctx.tr("info.title"), "\n".join(notes))

        def err(e):
            self.status.configure(text="")
            ctx.notify_videos_changed()  # variasi yang sudah jadi sebelum error tetap ditampilkan
            show_error(ctx, e)

        self.status.configure(text="AI…")
        ctx.bus.run(lambda: make_variations(svc, ctx.project, vid, 3, auto_check=auto, status=post), ok, err)

    # ================= thumbnail, ekspor, impor =================
    def generate_thumbs(self) -> None:
        ctx = self.ctx
        if not env_setup.is_installed(ctx.project):
            messagebox.showinfo(ctx.tr("info.title"), ctx.tr("ed.thumbs_env"))
            return
        ctx.flush()

        def work():
            return make_thumbs(ctx.project, on_progress=lambda n, t, name: ctx.bus.post(
                self.status.configure, text=f"{ctx.tr('ed.thumbs')} {n}/{t}: {name}"))

        def ok(result):
            made, errors = result
            self.status.configure(text=ctx.tr("ed.thumbs_done", n=made))
            self.refresh()
            if errors:
                show_error(ctx, "\n".join(errors[:3]))

        def err(e):
            self.status.configure(text="")
            show_error(ctx, e)

        ctx.bus.run(work, ok, err)

    def export_zip(self) -> None:
        ctx = self.ctx
        path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Vibe Motion project", "*.zip")],
                                            initialfile="vibemotion-project.zip")
        if not path:
            return
        ctx.flush()
        try:
            n = export_project(ctx.project, Path(path))
        except Exception as e:  # noqa: BLE001
            show_error(ctx, e)
            return
        messagebox.showinfo(ctx.tr("info.title"), ctx.tr("ed.exported", n=n))

    def import_zip(self) -> None:
        ctx = self.ctx
        path = filedialog.askopenfilename(filetypes=[("Vibe Motion project", "*.zip")])
        if not path:
            return
        ctx.flush()
        try:
            new = import_project(ctx.project, Path(path))
        except Exception as e:  # noqa: BLE001
            show_error(ctx, e)
            return
        if new:
            ctx.selected_id = new[0].id
        ctx.project.save()
        ctx.notify_videos_changed()
        messagebox.showinfo(ctx.tr("info.title"), ctx.tr("ed.imported", n=len(new)))

    # ================= AI =================
    def _service(self) -> AIService | None:
        try:
            return AIService(make_provider(self.ctx.settings, lambda m: self.ctx.bus.post(self.ctx.log, m), self.ctx.usage))
        except Exception as e:  # noqa: BLE001
            show_error(self.ctx, e)
            return None

    def _run_ai(self, work) -> None:
        self.send_btn.configure(state="disabled")
        self.status.configure(text="AI…")

        def ok(code: str) -> None:
            self.send_btn.configure(state="normal")
            self.status.configure(text="")
            self.backup = get_text(self.code)
            self.set_code(code)
            self.banner.pack(fill="x", before=self.code)

        def err(e: Exception) -> None:
            self.send_btn.configure(state="normal")
            self.status.configure(text="")
            show_error(self.ctx, e)

        self.ctx.bus.run(work, ok, err)

    def send(self) -> None:
        request = self.ask.get().strip()
        svc = self._service()
        if not request or not svc or self.backup is not None:
            return
        self.commit()
        it = self.ctx.selected
        spec = GenerationSpec(width=it.width, height=it.height, fps=it.fps, duration_sec=it.duration_sec,
                              assets=self.ctx.project.list_assets())
        code = it.code
        validator = make_validator(self.ctx.project, self.ctx.settings.auto_check)
        self.ask.delete(0, "end")
        self._run_ai(lambda: edit_checked(svc, code, request, spec, validator)[0])  # edit juga divalidasi & diperbaiki

    def auto_fix(self, error: str | None = None) -> None:
        svc = self._service()
        if not svc or self.backup is not None:
            return
        self.commit()
        code = self.ctx.selected.code
        err = error or self.ctx.last_error or "Periksa dan perbaiki kesalahan sintaks / impor."
        self._run_ai(lambda: svc.fix(code, err))

    def transcribe_media(self) -> None:
        ctx = self.ctx
        path = filedialog.askopenfilename(filetypes=[("Audio/Video", "*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.mp4 *.webm *.mov"),
                                                     ("All", "*.*")])
        svc = self._service() if path else None
        if not svc:
            return
        media = Path(path)
        self.status.configure(text=ctx.tr("ed.transcribing"))

        def work():
            caps = transcribe(svc, media)
            ctx.project.import_asset(media)
            return ctx.project.write_captions(caps, f"captions_{media.stem}")

        def ok(ref):
            self.status.configure(text="")
            messagebox.showinfo(ctx.tr("info.title"), ctx.tr("ed.transcribed", name=ref))

        def err(e):
            self.status.configure(text="")
            show_error(ctx, e)

        ctx.bus.run(work, ok, err)

    def approve(self) -> None:
        """Terima usulan AI: versi lama & baru sama-sama masuk riwayat."""
        vid, old = self._loaded_id, self.backup
        new = get_text(self.code)
        self.backup = None
        self.banner.pack_forget()
        if vid:
            item = self.ctx.project.get(vid)
            item.code = old if old is not None else item.code
            self.ctx.project.snapshot(vid, "sebelum-AI")
            item.code = new
        self.ctx.autofix_attempts = 0
        self.ctx.project.save()
        if vid:
            self.ctx.project.snapshot(vid, "AI edit")
        self._dirty = False
        self.status.configure(text=self.ctx.tr("ed.saved"))

    def reject(self) -> None:
        if self.backup is not None:
            self.set_code(self.backup)
        self.backup = None
        self.banner.pack_forget()
