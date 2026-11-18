"""Cek Node.js dan pasang dependensi proyek Remotion."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .project import Project
from .proc import IS_WIN, find_tool, run_capture

Log = Callable[[str], None]


class SetupError(RuntimeError):
    pass


def node_version() -> str | None:
    node = find_tool("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def install_node_windows(log: Log) -> bool:
    """Coba winget; kembalikan True bila node terdeteksi setelahnya."""
    winget = find_tool("winget")
    if not (IS_WIN and winget):
        return False
    log("Memasang Node.js LTS via winget…")
    run_capture([winget, "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--silent",
                 "--accept-package-agreements", "--accept-source-agreements"], Path.cwd(), log)
    return node_version() is not None


def is_installed(project: Project) -> bool:
    return (project.root / "node_modules" / "remotion").exists() and (project.root / "package.json").exists()


def setup_environment(project: Project, log: Log) -> None:
    """Scaffold proyek lalu `npm install`. Lempar SetupError bila gagal."""
    ver = node_version()
    if not ver and not install_node_windows(log):
        raise SetupError("Node.js tidak ditemukan. Pasang dari https://nodejs.org lalu ulangi.")
    npm = find_tool("npm")
    if not npm:
        raise SetupError("npm tidak ditemukan.")
    log(f"Node.js {node_version()}")
    project.save()
    log("npm install …")
    code = run_capture([npm, "install", "--no-audit", "--no-fund"], project.root, log)
    if code != 0:
        raise SetupError(f"npm install gagal (kode {code}).")
    log("Environment siap.")


def install_packages(project: Project, packages: list[str], log: Log) -> None:
    npm = find_tool("npm")
    if not npm:
        raise SetupError("npm tidak ditemukan.")
    pkgs = [p.strip() for p in packages if p.strip()]
    if not pkgs:
        raise SetupError("Tidak ada paket dipilih.")
    from .versions import REMOTION_VERSION
    pinned = [f"{p}@{REMOTION_VERSION}" if p.startswith("@remotion/") and "@" not in p[1:] else p for p in pkgs]
    code = run_capture([npm, "install", "--save-exact", "--no-audit", "--no-fund", *pinned], project.root, log)
    if code != 0:
        raise SetupError(f"Gagal memasang paket (kode {code}).")
