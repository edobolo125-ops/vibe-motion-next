from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..ai import skills
from ..ai.models import PRESETS, fetch_models, merge
from ..context import AppContext
from .dialogs import show_error
import os
import subprocess
import sys

from ..core import env_setup
from ..core.diagnostics import diagnostics_text
from ..ai.connection import check_connection
from ..core.logs import log_dir
from ..core.updater import check_update
from .. import __version__
from ..core.versions import OPTIONAL_PACKAGES
from .widgets import get_text, labeled_entry, labeled_menu, section, set_text


class SettingsTab(ctk.CTkScrollableFrame):
    def __init__(self, master, ctx: AppContext):
        super().__init__(master, fg_color="transparent")
        self.ctx = ctx
        s = ctx.settings
        section(self, ctx.tr("set.provider"))
        self.provider = labeled_menu(self, ctx.tr("set.provider"), ["gemini", "anthropic", "openai"], s.provider)
        ctk.CTkLabel(self, text=ctx.tr("set.keys"), anchor="w").pack(fill="x", padx=8, pady=(8, 0))
        self.keys = ctk.CTkTextbox(self, height=90)
        self.keys.pack(fill="x", padx=8, pady=2)
        set_text(self.keys, "\n".join(s.gemini_keys))
        self.gmodel = self._model_row("Gemini", "gemini", s.gemini_model)
        self.gfallbacks = labeled_entry(self, ctx.tr("set.fallback_models"), ", ".join(s.gemini_fallbacks))
        self.fallback_provider = labeled_menu(self, ctx.tr("set.fallback_provider"),
                                              ["none", "gemini", "anthropic", "openai"], s.fallback_provider)
        self.akey = labeled_entry(self, f"Anthropic (Claude) — {ctx.tr('set.key')}", s.anthropic_key, show="•")
        self.amodel = self._model_row("Anthropic (Claude)", "anthropic", s.anthropic_model)
        self.obase = labeled_entry(self, f"OpenAI-compatible — {ctx.tr('set.base')}", s.openai_base_url)
        self.okey = labeled_entry(self, f"OpenAI-compatible — {ctx.tr('set.key')}", s.openai_key, show="•")
        self.omodel = self._model_row("OpenAI-compatible", "openai", s.openai_model)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(10, 0))
        self.test_btn = ctk.CTkButton(row, text=ctx.tr("set.test_conn"), width=170, fg_color="#2a7", command=self.test_connection)
        self.test_btn.pack(side="left")
        ctk.CTkButton(row, text=ctx.tr("set.wizard_btn"), width=170, fg_color="gray40", command=self.open_wizard).pack(side="left", padx=6)
        self.price_in = labeled_entry(self, ctx.tr("set.price_in"), f"{s.price_in:g}" if s.price_in else "")
        self.price_out = labeled_entry(self, ctx.tr("set.price_out"), f"{s.price_out:g}" if s.price_out else "")

        section(self, ctx.tr("set.project"))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.project_dir = ctk.CTkEntry(row)
        self.project_dir.insert(0, s.project_dir)
        self.project_dir.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text=ctx.tr("set.browse"), width=90, command=self.browse).pack(side="left", padx=6)
        self.lang = labeled_menu(self, ctx.tr("set.language"), ["id", "en"], s.language)
        ctk.CTkButton(self, text=ctx.tr("set.save"), height=38, command=self.save).pack(fill="x", padx=8, pady=12)

        section(self, ctx.tr("set.diag"))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8)
        ctk.CTkButton(row, text=ctx.tr("set.open_log"), width=160, fg_color="gray40",
                      command=self.open_logs).pack(side="left")
        ctk.CTkButton(row, text=ctx.tr("set.copy_diag"), width=190, fg_color="gray40",
                      command=self.copy_diag).pack(side="left", padx=6)

        section(self, ctx.tr("set.update"))
        self.update_url = labeled_entry(self, ctx.tr("set.update_url"), s.update_url)
        self.check_startup = ctk.CTkCheckBox(self, text=ctx.tr("set.check_startup"))
        (self.check_startup.select if s.check_updates else self.check_startup.deselect)()
        self.check_startup.pack(anchor="w", padx=8, pady=4)
        ctk.CTkButton(self, text=ctx.tr("set.check_now"), width=160, fg_color="gray40",
                      command=self.check_now).pack(anchor="w", padx=8, pady=(0, 4))

        section(self, ctx.tr("set.skills"))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8)
        self.skill_in = ctk.CTkEntry(row, placeholder_text=ctx.tr("set.skill_in"))
        self.skill_in.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text=ctx.tr("set.install"), width=90, command=self.install_skill).pack(side="left", padx=6)
        self.skill_list = ctk.CTkFrame(self, fg_color="transparent")
        self.skill_list.pack(fill="x", padx=8, pady=4)
        self.refresh_skills()

        section(self, ctx.tr("set.packages"))
        self.pkg_vars = {}
        for name, desc in OPTIONAL_PACKAGES:
            var = ctk.BooleanVar()
            ctk.CTkCheckBox(self, text=f"{name} — {desc}", variable=var).pack(anchor="w", padx=12, pady=1)
            self.pkg_vars[name] = var
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        self.pkg_in = ctk.CTkEntry(row, placeholder_text=ctx.tr("set.pkg_in"))
        self.pkg_in.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text=ctx.tr("set.install"), width=90, command=self.install_packages).pack(side="left", padx=6)

    def _model_row(self, title: str, provider: str, current: str) -> ctk.CTkComboBox:
        ctk.CTkLabel(self, text=f"{title} — {self.ctx.tr('set.model')}", anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=2)
        box = ctk.CTkComboBox(row, values=merge(PRESETS[provider], [], current))
        box.set(current)
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="⟳ Refresh", width=90,
                      command=lambda: self.refresh_models(provider, box)).pack(side="left", padx=6)
        return box

    def _key_for(self, provider: str) -> str:
        if provider == "gemini":
            return next((k.strip() for k in get_text(self.keys).splitlines() if k.strip()), "")
        return (self.akey if provider == "anthropic" else self.okey).get().strip()

    def refresh_models(self, provider: str, box: ctk.CTkComboBox) -> None:
        ctx = self.ctx
        key, base = self._key_for(provider), self.obase.get().strip()

        def ok(models):
            box.configure(values=merge(PRESETS[provider], models, box.get()))
            messagebox.showinfo(ctx.tr("info.title"), f"{len(models)} model")

        def err(e):
            show_error(ctx, e)

        ctx.bus.run(lambda: fetch_models(provider, key, base), ok, err)

    def check_now(self) -> None:
        ctx = self.ctx
        url = self.update_url.get().strip()

        def ok(info):
            if info is None:
                messagebox.showinfo(ctx.tr("info.title"), ctx.tr("set.up_to_date", v=__version__))
            elif messagebox.askyesno(ctx.tr("info.title"), ctx.tr("set.update_found", v=info.version) + "\n\n" + info.notes[:300]):
                import webbrowser
                webbrowser.open(info.url)

        ctx.bus.run(lambda: check_update(url, __version__), ok, lambda e: show_error(ctx, e))

    def open_logs(self) -> None:
        path = str(log_dir())
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def copy_diag(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(diagnostics_text(self.ctx.settings))
        messagebox.showinfo(self.ctx.tr("info.title"), self.ctx.tr("set.diag_copied"))

    def browse(self) -> None:
        d = filedialog.askdirectory()
        if d:
            self.project_dir.delete(0, "end")
            self.project_dir.insert(0, d)

    def collect(self) -> None:
        """Salin isi form ke Settings (belum menulis disk)."""
        s, ctx = self.ctx.settings, self.ctx
        s.provider = self.provider.get()
        s.gemini_keys = [k.strip() for k in get_text(self.keys).splitlines() if k.strip()]
        s.gemini_model = self.gmodel.get().strip() or s.gemini_model
        s.gemini_fallbacks = [m.strip() for m in self.gfallbacks.get().split(",") if m.strip()]
        s.fallback_provider = self.fallback_provider.get()
        s.anthropic_key = self.akey.get().strip()
        s.anthropic_model = self.amodel.get().strip() or s.anthropic_model
        s.openai_base_url, s.openai_key = self.obase.get().strip(), self.okey.get().strip()
        s.openai_model = self.omodel.get().strip() or s.openai_model
        s.language = self.lang.get()
        s.update_url, s.check_updates = self.update_url.get().strip(), bool(self.check_startup.get())
        for attr, entry in (("price_in", self.price_in), ("price_out", self.price_out)):
            try:
                setattr(s, attr, max(0.0, float(entry.get().replace(",", ".") or 0)))
            except ValueError:
                setattr(s, attr, 0.0)
        ctx.usage.price_in, ctx.usage.price_out = s.price_in, s.price_out
        ctx.usage_changed()

    def save(self) -> None:
        s, ctx = self.ctx.settings, self.ctx
        old_lang = s.language
        self.collect()
        new_dir = self.project_dir.get().strip()
        if new_dir and new_dir != s.project_dir:
            ctx.flush()
            ctx.set_project_dir(new_dir)
        s.save()
        msg = ctx.tr("set.saved") + (f"\n{ctx.tr('set.restart')}" if s.language != old_lang else "")
        messagebox.showinfo(ctx.tr("info.title"), msg)

    def test_connection(self) -> None:
        """Simpan dulu isi form (supaya yang diuji = yang terlihat), lalu uji provider terpilih."""
        ctx = self.ctx
        self.collect()
        ctx.settings.save()
        self.test_btn.configure(state="disabled", text=ctx.tr("set.test_running"))

        def done(result):
            self.test_btn.configure(state="normal", text=ctx.tr("set.test_conn"))
            (messagebox.showinfo if result.ok else messagebox.showwarning)(ctx.tr("info.title"), result.message)

        ctx.bus.run(lambda: check_connection(ctx.settings), done,
                    lambda e: (self.test_btn.configure(state="normal", text=ctx.tr("set.test_conn")), show_error(ctx, e)))

    def open_wizard(self) -> None:
        from .wizard import Wizard
        Wizard(self, self.ctx)

    # ---------- skills ----------
    def refresh_skills(self) -> None:
        for w in self.skill_list.winfo_children():
            w.destroy()
        for name in skills.list_skills():
            row = ctk.CTkFrame(self.skill_list, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text=name, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=30, fg_color="#a33",
                          command=lambda n=name: (skills.remove_skill(n), self.refresh_skills())).pack(side="right")

    def install_skill(self) -> None:
        text, ctx = self.skill_in.get().strip(), self.ctx

        def err(e):
            show_error(ctx, e)

        def ok(names):
            self.skill_in.delete(0, "end")
            self.refresh_skills()
            messagebox.showinfo(ctx.tr("info.title"), "\n".join(names))

        ctx.bus.run(lambda: skills.install_skill(text), ok, err)

    # ---------- npm ----------
    def install_packages(self) -> None:
        ctx = self.ctx
        pkgs = [n for n, v in self.pkg_vars.items() if v.get()] + self.pkg_in.get().split()
        if not env_setup.is_installed(ctx.project):
            messagebox.showinfo(ctx.tr("info.title"), ctx.tr("run.setup"))
            return
        ctx.flush()

        def err(e):
            show_error(ctx, e)

        ctx.bus.run(lambda: env_setup.install_packages(ctx.project, pkgs, lambda l: ctx.bus.post(ctx.log, l)),
                    lambda _r: messagebox.showinfo(ctx.tr("info.title"), "OK"), err)
