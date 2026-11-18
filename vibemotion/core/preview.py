"""Remotion Studio sebagai proses latar belakang + pemantau error kompilasi."""
from __future__ import annotations

import re
import socket
import subprocess
import threading
from pathlib import Path
from typing import Callable

from .proc import find_tool, kill_tree, popen, pump_lines

_URL = re.compile(r"(https?://localhost:\d+)")
_ERR_START = re.compile(r"^(?:ERROR|Error)\b.*?in\s+(\./src/\S+)|^Module not found|^SyntaxError|^error TS\d+", re.I)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ErrorCollector:
    """Mengumpulkan blok error kompilasi dari log Studio (webpack/esbuild)."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._collecting = False

    def feed(self, line: str) -> None:
        if _ERR_START.search(line) or line.startswith("ERROR in"):
            self.lines = [line]
            self._collecting = True
        elif self._collecting:
            if line.startswith(("Built in", "Building", "Server ready")):
                self._collecting = False
            elif len(self.lines) < 25:
                self.lines.append(line)
        if line.startswith("Built in") and not self._collecting:
            pass

    def clear(self) -> None:
        self.lines, self._collecting = [], False

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


class PreviewServer:
    def __init__(self, root: Path, on_log: Callable[[str], None], on_error: Callable[[str], None] | None = None):
        self.root = Path(root)
        self.on_log = on_log
        self.on_error = on_error
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.url: str | None = None
        self.errors = ErrorCollector()
        self._ready = threading.Event()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout: float = 90) -> str:
        if self.running and self.url:
            return self.url
        npx = find_tool("npx")
        if not npx:
            raise RuntimeError("npx tidak ditemukan; pasang Node.js.")
        self.port = free_port()
        self._ready.clear()
        self.errors.clear()
        self.proc = popen([npx, "remotion", "studio", "src/index.ts", "--port", str(self.port), "--no-open"], self.root)
        self.url = f"http://localhost:{self.port}"
        pump_lines(self.proc, self._handle)
        if not self._ready.wait(timeout):
            self.stop()
            raise RuntimeError("Studio tidak siap dalam waktu yang ditentukan.")
        return self.url

    def _handle(self, line: str) -> None:
        self.on_log(line)
        if "Server ready" in line or _URL.search(line):
            self._ready.set()
        self.errors.feed(line)
        if line.startswith("Built in") and self.errors.text and self.on_error:
            self.on_error(self.errors.text)
            self.errors.clear()

    def stop(self) -> None:
        kill_tree(self.proc)
        self.proc, self.url = None, None
