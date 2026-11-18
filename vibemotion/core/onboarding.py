"""Pemeriksaan kesiapan untuk panduan pertama kali (murni, mudah diuji)."""
from __future__ import annotations

from dataclasses import dataclass

from . import env_setup
from .project import Project


@dataclass(frozen=True)
class Step:
    key: str    # node | key | env
    ok: bool
    detail: str = ""


def check_steps(settings, project: Project) -> list[Step]:
    node = env_setup.node_version()
    keys = settings.active_key_count()
    return [
        Step("node", bool(node), node or ""),
        Step("key", keys > 0, str(keys) if keys else ""),
        Step("env", env_setup.is_installed(project)),
    ]


def all_ready(steps: list[Step]) -> bool:
    return all(s.ok for s in steps)
