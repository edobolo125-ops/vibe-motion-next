"""Thumbnail video (frame tengah, kecil) di cache; dibuat ulang hanya bila kode/ukuran berubah."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from .project import Project, VideoItem
from .render import render_still

StillFn = Callable[[Project, VideoItem, Path], Path]


def thumb_dir(project: Project) -> Path:
    return project.root / ".vm_thumbs"


def thumb_path(project: Project, item: VideoItem) -> Path:
    key = f"{item.code}|{item.width}|{item.height}|{item.fps}|{item.frames}".encode("utf-8")
    return thumb_dir(project) / f"{item.id}-{hashlib.sha1(key).hexdigest()[:10]}.png"


def existing_thumb(project: Project, item: VideoItem) -> Path | None:
    p = thumb_path(project, item)
    return p if p.exists() else None


def default_still(extra_args: list[str] | None = None) -> StillFn:
    return lambda project, item, out: render_still(project, item, out, scale=0.25, extra_args=extra_args)


def make_thumbs(project: Project, still: StillFn | None = None,
                on_progress: Callable[[int, int, str], None] = lambda *_: None) -> tuple[int, list[str]]:
    """Buat thumbnail yang belum ada/usang. Kembalikan (jumlah dibuat, daftar error)."""
    still = still or default_still()
    todo = [i for i in project.items if not thumb_path(project, i).exists()]
    made, errors = 0, []
    for n, item in enumerate(todo, 1):
        on_progress(n, len(todo), item.name)
        target = thumb_path(project, item)
        try:
            still(project, item, target)
        except Exception as e:  # noqa: BLE001 — satu gagal tidak menghentikan yang lain
            errors.append(f"{item.name}: {e}")
            continue
        made += 1
        for old in thumb_dir(project).glob(f"{item.id}-*.png"):  # buang versi usang
            if old != target:
                try:
                    old.unlink()
                except OSError:
                    pass
    return made, errors
