"""Info diagnostik yang aman dibagikan (tanpa API key)."""
from __future__ import annotations

import platform
import sys

from .. import __version__
from .env_setup import node_version
from .paths import app_data_dir


def diagnostics_text(settings) -> str:
    keys = len(getattr(settings, "gemini_keys", []))
    lines = [
        f"Vibe Motion Next v{__version__}",
        f"Python {sys.version.split()[0]} — {platform.platform()}",
        f"Node: {node_version() or 'TIDAK TERDETEKSI'}",
        f"Provider: {settings.provider} | model: "
        + {"gemini": settings.gemini_model, "anthropic": settings.anthropic_model}.get(settings.provider, settings.openai_model),
        f"Key terisi — gemini:{keys} anthropic:{'ya' if settings.anthropic_key else 'tidak'} "
        f"openai:{'ya' if settings.openai_key else 'tidak'}",
        f"Folder proyek: {settings.project_dir}",
        f"Folder data: {app_data_dir()}",
    ]
    return "\n".join(lines)
