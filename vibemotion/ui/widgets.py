from __future__ import annotations

import customtkinter as ctk

MONO = ("Consolas", 12)


class LogBox(ctk.CTkTextbox):
    """Kotak log hanya-baca dengan batas baris."""

    def __init__(self, master, max_lines: int = 800, **kw):
        super().__init__(master, font=MONO, wrap="none", **kw)
        self.max_lines = max_lines
        self.configure(state="disabled")

    def append(self, line: str) -> None:
        self.configure(state="normal")
        self.insert("end", line + "\n")
        count = int(self.index("end-1c").split(".")[0])
        if count > self.max_lines:
            self.delete("1.0", f"{count - self.max_lines}.0")
        self.see("end")
        self.configure(state="disabled")

    def clear(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


def section(master, text: str) -> ctk.CTkLabel:
    lbl = ctk.CTkLabel(master, text=text, font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
    lbl.pack(fill="x", padx=8, pady=(12, 2))
    return lbl


def labeled_entry(master, text: str, value: str = "", show: str | None = None) -> ctk.CTkEntry:
    ctk.CTkLabel(master, text=text, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
    e = ctk.CTkEntry(master, show=show)
    e.pack(fill="x", padx=8, pady=2)
    if value:
        e.insert(0, value)
    return e


def labeled_menu(master, text: str, values: list[str], value: str | None = None) -> ctk.CTkOptionMenu:
    ctk.CTkLabel(master, text=text, anchor="w").pack(fill="x", padx=8, pady=(6, 0))
    m = ctk.CTkOptionMenu(master, values=values)
    m.pack(fill="x", padx=8, pady=2)
    if value in values:
        m.set(value)
    return m


def get_text(box: ctk.CTkTextbox) -> str:
    return box.get("1.0", "end-1c")


def set_text(box: ctk.CTkTextbox, text: str) -> None:
    box.delete("1.0", "end")
    box.insert("1.0", text)
