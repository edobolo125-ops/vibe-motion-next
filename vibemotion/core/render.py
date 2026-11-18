"""Render video via `npx remotion render` dengan progres dan pembatalan."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .code_utils import safe_filename
from .project import Project, VideoItem
from .proc import find_tool, kill_tree, popen, pump_lines

FORMATS = {
    "mp4": ["--codec", "h264"],
    "webm": ["--codec", "vp9"],
    "gif": ["--codec", "gif"],
    "mov": ["--codec", "prores", "--prores-profile", "4444"],
}
_PROGRESS = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass
class RenderOptions:
    fmt: str = "mp4"
    concurrency: int = 0
    hardware_acceleration: str = "if-possible"
    scale: float = 1.0  # 1.0 = penuh; <1 = draft cepat


def build_command(npx: str, item: VideoItem, out: Path, opts: RenderOptions) -> list[str]:
    if opts.fmt not in FORMATS:
        raise ValueError(f"format tidak didukung: {opts.fmt}")
    cmd = [npx, "remotion", "render", "src/index.ts", item.comp_id, str(out), *FORMATS[opts.fmt],
           "--log=info", f"--hardware-acceleration={opts.hardware_acceleration}"]
    if opts.concurrency > 0:
        cmd += ["--concurrency", str(opts.concurrency)]
    if opts.scale and abs(opts.scale - 1.0) > 1e-6 and opts.fmt != "gif":
        cmd += [f"--scale={opts.scale:g}"]
    return cmd


def parse_progress(line: str) -> float | None:
    m = _PROGRESS.search(line)
    if m and ("Rendered" in line or "Encoded" in line or "Rendering" in line):
        done, total = int(m.group(1)), int(m.group(2))
        if total:
            return min(1.0, done / total)
    return None


class RenderQueue:
    """Antrean render berurutan; satu thread, bisa dibatalkan."""

    def __init__(self, project: Project, export_dir: Path, opts: RenderOptions,
                 on_log: Callable[[str], None], on_progress: Callable[[str, float], None],
                 on_done: Callable[[str, Path | None, str | None], None]):
        self.project, self.export_dir, self.opts = project, Path(export_dir), opts
        self.on_log, self.on_progress, self.on_done = on_log, on_progress, on_done
        self._cancel = threading.Event()
        self._proc = None
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, video_ids: list[str]) -> None:
        if self.busy:
            raise RuntimeError("Render sedang berjalan.")
        self._cancel.clear()
        self.project.save()
        self._thread = threading.Thread(target=self._run, args=(list(video_ids),), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        kill_tree(self._proc)

    def _run(self, ids: list[str]) -> None:
        npx = find_tool("npx")
        self.export_dir.mkdir(parents=True, exist_ok=True)
        for vid in ids:
            if self._cancel.is_set():
                break
            item = self.project.get(vid)
            out = self.export_dir / f"{safe_filename(item.name)}.{self.opts.fmt}"
            if not npx:
                self.on_done(vid, None, "npx tidak ditemukan; pasang Node.js.")
                continue
            self.on_log(f"▶ Render {item.name} → {out}")
            self._proc = popen(build_command(npx, item, out, self.opts), self.project.root)
            tail: list[str] = []

            def handle(line: str, vid=vid, tail=tail) -> None:
                self.on_log(line)
                tail.append(line)
                del tail[:-15]
                p = parse_progress(line)
                if p is not None:
                    self.on_progress(vid, p)

            t = pump_lines(self._proc, handle)
            code = self._proc.wait()
            t.join(timeout=2)
            if self._cancel.is_set():
                self.on_done(vid, None, "dibatalkan")
            elif code == 0:
                self.on_progress(vid, 1.0)
                self.on_done(vid, out, None)
            else:
                self.on_done(vid, None, "\n".join(tail[-8:]) or f"exit {code}")


def render_still(project: Project, item: VideoItem, out: Path, frame: int | None = None, scale: float = 0.5,
                 extra_args: list[str] | None = None, timeout: int = 240) -> Path:
    """Render satu frame PNG (default: tengah video) — dipakai tinjauan visual & thumbnail."""
    npx = find_tool("npx")
    if not npx:
        raise RuntimeError("npx tidak ditemukan; pasang Node.js.")
    frame = item.frames // 2 if frame is None else max(0, min(item.frames - 1, frame))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [npx, "remotion", "still", "src/index.ts", item.comp_id, str(out), f"--frame={frame}", f"--scale={scale:g}",
           *(extra_args or [])]
    proc = popen(cmd, project.root)
    tail: list[str] = []
    pump = pump_lines(proc, lambda l: (tail.append(l), tail.__delitem__(slice(0, -12))))
    try:
        code = proc.wait(timeout=timeout)
    except Exception:  # noqa: BLE001 — timeout
        kill_tree(proc)
        raise RuntimeError("Render frame terlalu lama.")
    pump.join(timeout=2)
    if code != 0 or not out.exists():
        raise RuntimeError("Render frame gagal: " + " | ".join(tail[-4:]))
    return out
