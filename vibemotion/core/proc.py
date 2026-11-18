"""Pembantu subprocess lintas platform (tanpa jendela konsol, kill seluruh pohon proses)."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Sequence

IS_WIN = os.name == "nt"


def find_tool(name: str) -> str | None:
    """Cari node/npm/npx; di Windows termasuk lokasi instalasi standar."""
    found = shutil.which(name)
    if found:
        return found
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for ext in (".cmd", ".exe"):
                cand = Path(base) / "nodejs" / f"{name}{ext}"
                if cand.exists():
                    return str(cand)
    return None


def popen(cmd: Sequence[str], cwd: Path | str, env: dict | None = None) -> subprocess.Popen:
    kwargs: dict = dict(
        cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, **(env or {})}, bufsize=1,
    )
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(list(cmd), **kwargs)


def kill_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass


_CTRL = __import__("re").compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _CTRL.sub("", text)


def pump_lines(proc: subprocess.Popen, on_line: Callable[[str], None]) -> threading.Thread:
    """Baca output baris demi baris (\\r juga dianggap pemisah, untuk progress bar)."""

    def run() -> None:
        buf = ""
        assert proc.stdout is not None
        while True:
            ch = proc.stdout.read(1)
            if ch == "":
                break
            if ch in "\r\n":
                if buf.strip():
                    on_line(strip_ansi(buf))
                buf = ""
            else:
                buf += ch
        if buf.strip():
            on_line(strip_ansi(buf))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def run_capture(cmd: Sequence[str], cwd: Path | str, on_line: Callable[[str], None] | None = None) -> int:
    proc = popen(cmd, cwd)
    t = pump_lines(proc, on_line or (lambda _l: None))
    code = proc.wait()
    t.join(timeout=2)
    return code


__all__ = ["find_tool", "popen", "kill_tree", "pump_lines", "run_capture", "strip_ansi", "sys"]
