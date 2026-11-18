"""Preset ukuran/FPS untuk platform populer."""
from __future__ import annotations

from .project import VideoItem

RENDER_PRESETS: dict[str, tuple[int, int, int]] = {
    "YouTube 1080p (16:9)": (1920, 1080, 30),
    "YouTube 4K (16:9)": (3840, 2160, 30),
    "TikTok / Reels / Shorts (9:16)": (1080, 1920, 30),
    "Instagram Feed (4:5)": (1080, 1350, 30),
    "Instagram Square (1:1)": (1080, 1080, 30),
    "Poster / Cerita (2:3)": (1080, 1620, 30),
    "Sinematik (21:9, 24 fps)": (2560, 1080, 24),
}


def apply_preset(item: VideoItem, key: str) -> VideoItem:
    w, h, fps = RENDER_PRESETS[key]
    item.width, item.height, item.fps = w, h, fps
    return item
