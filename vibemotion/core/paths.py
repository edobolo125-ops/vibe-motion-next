"""Lokasi folder data aplikasi (lintas platform)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "VibeMotionNext"


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_project_dir() -> Path:
    return app_data_dir() / "remotion-project"


def default_export_dir() -> Path:
    return Path.home() / "Videos" / APP_NAME if os.name == "nt" else Path.home() / APP_NAME / "exports"


def skills_dir() -> Path:
    path = app_data_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path
