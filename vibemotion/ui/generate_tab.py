from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..ai.prompts import STYLE_OPTIONS, GenerationSpec
from ..ai.pipeline import generate_videos
from ..ai.service import AIService, make_provider, model_name, with_model
from ..config import RATIOS
from ..context import AppContext
from .dialogs import show_error
from ..core.code_utils import parse_duration_to_seconds
from ..core.library import SavedPrompts, UserTemplates
from ..templates import TEMPLATES
from .widgets import get_text, labeled_entry, labeled_menu, section


class GenerateTab(ctk.CTkFrame):
    def __init__(self, master, ctx: AppContext):
        super().__init__(master, fg_color="transparent")
        self.ctx, self.images = ctx, []
        s = ctx.settings
        left = ctk.CTkScrollableFrame(self, width=330, label_text=ctx.tr("gen.options"))
        left.pack(side="left", fill="y", padx=(0, 12))
        self.ratio = labeled_menu(left, ctx.tr("gen.ratio"), list(RATIOS), s.ratio)
        self.fps = labeled_menu(left, "FPS", ["24", "30", "60"], str(s.fps))
        self.duration = labeled_entry(left, ctx.tr("gen.duration"), f"{s.duration_sec:g}")
        self.theme = labeled_entry(left, ctx.tr("gen.theme"))
        self.style_menus = {k: labeled_menu(left, ctx.tr(f"style.{k}"), v, "Auto")
                            for k, v in STYLE_OPTIONS.items()}
        self.count = labeled_entry(left, ctx.tr("gen.count"), "1")
        self.mode_names = {ctx.tr("gen.mode_single"): "single", ctx.tr("gen.mode_story"): "storyboard"}
        self.mode = labeled_menu(left, ctx.tr("gen.mode"), list(self.mode_names), ctx.tr("gen.mode_single"))
        self.scenes = labeled_entry(left, ctx.tr("gen.scenes"), "3")
        self.merge = ctk.CTkCheckBox(left, text=ctx.tr("gen.merge"))
        self.merge.select()
        self.merge.pack(anchor="w", padx=8, pady=(6, 2))
        self.compare = ctk.CTkCheckBox(left, text=ctx.tr("gen.compare"))
        self.compare.pack(anchor="w", padx=8, pady=(10, 2))
        self.compare_model = labeled_entry(left, ctx.tr("gen.compare_model"))
        self.auto = ctk.CTkCheckBox(left, text=ctx.tr("gen.auto"))
        self.visual = ctk.CTkCheckBox(left, text=ctx.tr("gen.visual"))
        for box, on in ((self.auto, s.auto_check), (self.visual, s.visual_review)):
            box.pack(anchor="w", padx=8, pady=2)
            (box.select if on else box.deselect)()

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        section(right, ctx.tr("gen.instruction"))
        self.instruction = ctk.CTkTextbox(right, height=220, wrap="word")
        self.instruction.pack(fill="both", expand=True, padx=8)
        self.instruction.insert("1.0", s.last_instruction)
        prow = ctk.CTkFrame(right, fg_color="transparent")
        prow.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(prow, text=ctx.tr("gen.prompts") + ":").pack(side="left")
        self.prompts = SavedPrompts()
        self.prompt_menu = ctk.CTkOptionMenu(prow, values=["—"], width=220, command=self.load_prompt)
        self.prompt_menu.pack(side="left", padx=6)
        ctk.CTkButton(prow, text=ctx.tr("gen.prompt_save"), width=120, fg_color="gray40", command=self.save_prompt).pack(side="left")
        ctk.CTkButton(prow, text=ctx.tr("gen.prompt_del"), width=80, fg_color="#a33", command=self.delete_prompt).pack(side="left", padx=4)
        self.reload_prompts()
        section(right, ctx.tr("gen.extra"))
        self.extra = ctk.CTkEntry(right)
        self.extra.pack(fill="x", padx=8)
        section(right, ctx.tr("gen.refs"))
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", padx=8)
        ctk.CTkButton(row, text=ctx.tr("gen.pick"), width=140, command=self.pick_images).pack(side="left")
        ctk.CTkButton(row, text=ctx.tr("gen.clear"), width=90, fg_color="gray40",
                      command=self.clear_images).pack(side="left", padx=6)
        self.img_label = ctk.CTkLabel(right, text="—", anchor="w", justify="left")
        self.img_label.pack(fill="x", padx=8, pady=4)
        self.btn = ctk.CTkButton(right, text=ctx.tr("gen.go"), height=42, command=self.generate)
        self.btn.pack(fill="x", padx=8, pady=(10, 4))
        self.status = ctk.CTkLabel(right, text="", anchor="w", justify="left", wraplength=640)
        self.status.pack(fill="x", padx=8)
        section(right, ctx.tr("gen.template"))
        trow = ctk.CTkFrame(right, fg_color="transparent")
        trow.pack(fill="x", padx=8, pady=(0, 8))
        lang = ctx.settings.language
        self.tpl_names: dict[str, str] = {}
        self.user_templates: dict[str, object] = {}
        self.tpl = ctk.CTkOptionMenu(trow, values=["—"], width=260)
        self.tpl.pack(side="left")
        self.reload_templates()
        ctx.actions["reload_templates"] = self.reload_templates
        ctk.CTkButton(trow, text=ctx.tr("gen.template_go"), width=170, command=self.from_template).pack(side="left", padx=6)

    def pick_images(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif")])
        if files:
            self.images = [Path(f) for f in files]
            self.img_label.configure(text="\n".join(p.name for p in self.images[:6]) +
                                     (f"\n… +{len(self.images) - 6}" if len(self.images) > 6 else ""))

    def clear_images(self) -> None:
        self.images = []
        self.img_label.configure(text="—")

    def spec(self) -> GenerationSpec:
        w, h = RATIOS[self.ratio.get()]
        return GenerationSpec(
            width=w, height=h, fps=int(self.fps.get()),
            duration_sec=parse_duration_to_seconds(self.duration.get()), theme=self.theme.get().strip(),
            styles={k: m.get() for k, m in self.style_menus.items()},
            assets=self.ctx.project.list_assets(), extra=self.extra.get().strip())

    # ---------- pustaka pribadi ----------
    def reload_templates(self) -> None:
        lang = self.ctx.settings.language
        names = {(t.label_id if lang == "id" else t.label_en): k for k, t in TEMPLATES.items()}
        self.user_templates = {f"★ {t.name}": t for t in UserTemplates().list()}
        self.tpl_names = {**names, **{label: label for label in self.user_templates}}
        current = self.tpl.get()
        self.tpl.configure(values=list(self.tpl_names))
        self.tpl.set(current if current in self.tpl_names else next(iter(self.tpl_names)))

    def reload_prompts(self) -> None:
        names = self.prompts.names()
        self.prompt_menu.configure(values=names or ["—"])
        self.prompt_menu.set(names[0] if names else self.ctx.tr("gen.pick_prompt"))

    def load_prompt(self, name: str) -> None:
        try:
            text = self.prompts.get(name)
        except KeyError:
            return
        self.instruction.delete("1.0", "end")
        self.instruction.insert("1.0", text)

    def save_prompt(self) -> None:
        dlg = ctk.CTkInputDialog(text=self.ctx.tr("gen.prompt_name"), title=self.ctx.tr("gen.prompt_save"))
        name = dlg.get_input()
        if name:
            self.save_prompt_as(name)

    def save_prompt_as(self, name: str) -> None:
        try:
            self.prompts.save(name, get_text(self.instruction))
        except ValueError as e:
            show_error(self.ctx, e)
            return
        self.reload_prompts()
        self.prompt_menu.set(name.strip()[:60])

    def delete_prompt(self) -> None:
        if self.prompts.delete(self.prompt_menu.get()):
            self.reload_prompts()

    def from_template(self) -> None:
        ctx = self.ctx
        label = self.tpl.get()
        t = self.user_templates.get(label) or TEMPLATES[self.tpl_names[label]]
        sp = self.spec()
        item = ctx.project.add(t.code, label.lstrip("★ ").strip() if label in self.user_templates else label,
                               width=sp.width, height=sp.height, fps=sp.fps, duration_sec=t.seconds)
        ctx.selected_id = item.id
        ctx.project.save()
        ctx.notify_videos_changed()
        ctx.show_tab("editor")

    def generate(self) -> None:
        ctx, s = self.ctx, self.ctx.settings
        try:
            svc = AIService(make_provider(s, lambda m: ctx.bus.post(ctx.log, m), ctx.usage))
            count = max(1, min(10, int(self.count.get() or 1)))
            scenes = max(2, min(12, int(self.scenes.get() or 3)))
        except Exception as e:  # noqa: BLE001 — key kosong, angka salah, atau error tak terduga: tampilkan ramah
            show_error(ctx, e)
            return
        spec, instruction, images = self.spec(), get_text(self.instruction), list(self.images)
        mode = self.mode_names[self.mode.get()]
        auto, visual, merge = bool(self.auto.get()), bool(self.visual.get()), bool(self.merge.get())
        s.last_instruction, s.ratio, s.fps, s.duration_sec = instruction, self.ratio.get(), spec.fps, spec.duration_sec
        s.auto_check, s.visual_review = auto, visual
        s.save()
        ctx.flush()  # di thread UI: simpan editor + tulis file proyek (validator & render butuh file terbaru)
        self.btn.configure(state="disabled")
        post = lambda text: ctx.bus.post(self.status.configure, text=f"{ctx.tr('gen.working')} {text}")

        compare_to = self.compare_model.get().strip() if self.compare.get() else ""
        try:
            svc2 = AIService(make_provider(with_model(s, compare_to), lambda m: ctx.bus.post(ctx.log, m), ctx.usage)) if compare_to else None
        except Exception as e:  # noqa: BLE001
            show_error(ctx, e)
            self.btn.configure(state="normal")
            return
        primary_label = model_name(s) if compare_to else ""

        def work():
            kw = dict(mode=mode, count=count, scenes=scenes, merge=merge, auto_check=auto, visual_review=visual, status=post)
            items, notes = generate_videos(svc, ctx.project, spec, instruction, images, label=primary_label, **kw)
            if svc2 is not None:  # prompt yang sama dengan model pembanding → hasil berdampingan di daftar
                items2, notes2 = generate_videos(svc2, ctx.project, spec, instruction, images, label=compare_to, **kw)
                items, notes = items + items2, notes + notes2
            return items, notes

        def finish():
            self.btn.configure(state="normal")
            ctx.notify_videos_changed()

        def ok(result):
            items, notes = result
            ctx.selected_id = items[-1].id
            ctx.project.save()
            finish()
            msg = ctx.tr("gen.done", n=len(items))
            self.status.configure(text=msg + ("\n" + ctx.tr("gen.notes") + "\n" + "\n".join(notes) if notes else ""))
            ctx.show_tab("editor")

        def err(e):
            finish()
            self.status.configure(text="")
            show_error(ctx, e)

        ctx.bus.run(work, ok, err)
