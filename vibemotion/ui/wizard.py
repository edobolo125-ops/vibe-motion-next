"""Panduan awal: tiga prasyarat dengan status dan tombol aksi langsung."""
from __future__ import annotations

import webbrowser

import customtkinter as ctk

from ..ai.connection import check_connection
from ..context import AppContext
from ..core.onboarding import all_ready, check_steps

GREEN, RED = "#2fb344", "#e5534b"


class Wizard(ctk.CTkToplevel):
    def __init__(self, master, ctx: AppContext):
        super().__init__(master)
        self.ctx = ctx
        self.title(ctx.tr("wizard.title"))
        self.geometry("620x470")
        self.lift()
        ctk.CTkLabel(self, text=ctx.tr("wizard.title"), font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=20, pady=(16, 2))
        ctk.CTkLabel(self, text=ctx.tr("wizard.intro"), wraplength=570, justify="left", anchor="w").pack(anchor="w", padx=20, pady=(0, 10))

        self.rows: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel, ctk.CTkButton]] = {}
        for key in ("node", "key", "env"):
            row = ctk.CTkFrame(self)
            row.pack(fill="x", padx=20, pady=4)
            mark = ctk.CTkLabel(row, text="•", width=28, font=ctk.CTkFont(size=18, weight="bold"))
            mark.pack(side="left", padx=(8, 2), pady=10)
            texts = ctk.CTkFrame(row, fg_color="transparent")
            texts.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(texts, text=ctx.tr(f"wizard.{key}"), anchor="w", font=ctk.CTkFont(weight="bold")).pack(fill="x")
            detail = ctk.CTkLabel(texts, text="", anchor="w", justify="left", wraplength=340, text_color=("gray30", "gray70"))
            detail.pack(fill="x")
            btn = ctk.CTkButton(row, text="", width=150, command=lambda k=key: self.act(k))
            btn.pack(side="right", padx=10)
            self.rows[key] = (mark, detail, btn)

        self.result = ctk.CTkLabel(self, text="", wraplength=570, justify="left", anchor="w")
        self.result.pack(fill="x", padx=22, pady=(6, 0))
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=20, pady=14)
        self.dont_show = ctk.CTkCheckBox(bottom, text=ctx.tr("wizard.dont_show"))
        self.dont_show.select()
        self.dont_show.pack(side="left")
        ctk.CTkButton(bottom, text=ctx.tr("wizard.close"), width=100, command=self.close).pack(side="right")
        ctk.CTkButton(bottom, text=ctx.tr("wizard.recheck"), width=130, fg_color="gray40", command=self.refresh).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    # ---- status ----
    def refresh(self) -> None:
        ctx = self.ctx
        steps = check_steps(ctx.settings, ctx.project)
        for step in steps:
            mark, detail, btn = self.rows[step.key]
            mark.configure(text="✔" if step.ok else "✘", text_color=GREEN if step.ok else RED)
            if step.key == "node":
                detail.configure(text=step.detail or ctx.tr("wizard.not_ready"))
                btn.configure(text=ctx.tr("wizard.btn_node"), state="disabled" if step.ok else "normal")
            elif step.key == "key":
                detail.configure(text=(ctx.tr("wizard.key_count", n=step.detail) if step.ok else ctx.tr("wizard.not_ready"))
                                 + f" — {ctx.settings.provider}")
                btn.configure(text=ctx.tr("wizard.btn_key_test" if step.ok else "wizard.btn_key_set"), state="normal")
            else:
                detail.configure(text="" if step.ok else ctx.tr("wizard.not_ready"))
                btn.configure(text=ctx.tr("wizard.btn_env"), state="disabled" if step.ok else "normal")
        if all_ready(steps):
            self.result.configure(text=ctx.tr("wizard.done"), text_color=GREEN)

    def act(self, key: str) -> None:
        ctx = self.ctx
        if key == "node":
            webbrowser.open("https://nodejs.org")
        elif key == "env":
            fn = ctx.actions.get("setup_env")
            if fn:
                ctx.show_tab("run")
                fn()
        elif ctx.settings.active_key_count() == 0:
            ctx.show_tab("settings")
        else:  # tes koneksi
            self.result.configure(text=ctx.tr("set.test_running"), text_color=("gray30", "gray70"))

            def done(r) -> None:
                self.result.configure(text=r.message, text_color=GREEN if r.ok else RED)

            ctx.bus.run(lambda: check_connection(ctx.settings), done,
                        lambda e: self.result.configure(text=str(e), text_color=RED))

    def close(self) -> None:
        if self.dont_show.get():
            self.ctx.settings.onboarded = True
            self.ctx.settings.save()
        self.destroy()
