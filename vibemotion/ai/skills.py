"""Skill GitHub (SKILL.md) sebagai tambahan panduan untuk AI."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import requests

from ..core.paths import skills_dir

_REPO = re.compile(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
MAX_SKILL_CHARS = 6000
MAX_TOTAL_CHARS = 20000


def parse_repo(text: str) -> tuple[str, str]:
    m = _REPO.match(text.strip().removesuffix("/"))
    if not m:
        raise ValueError("Format harus owner/repo atau URL GitHub.")
    return m.group(1), m.group(2)


def install_skill(text: str, session: requests.Session | None = None, dest: Path | None = None) -> list[str]:
    """Unduh semua SKILL.md dari repo. Kembalikan nama skill yang terpasang."""
    http = session or requests.Session()
    owner, repo = parse_repo(text)
    tree = http.get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1", timeout=30)
    if tree.status_code != 200:
        raise RuntimeError(f"Repo tidak ditemukan / tidak bisa diakses ({tree.status_code}).")
    paths = [n["path"] for n in tree.json().get("tree", [])
             if n.get("type") == "blob" and n["path"].split("/")[-1].upper() == "SKILL.MD"][:20]
    if not paths:
        raise RuntimeError("Tidak ada SKILL.md di repositori itu.")
    base = dest or skills_dir()
    names = []
    for p in paths:
        raw = http.get(f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{p}", timeout=30)
        if raw.status_code != 200:
            continue
        sub = "/".join(p.split("/")[:-1]).replace("/", "__")
        name = f"{owner}__{repo}" + (f"__{sub}" if sub else "")
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(raw.text, encoding="utf-8")
        names.append(name)
    if not names:
        raise RuntimeError("Gagal mengunduh SKILL.md.")
    return names


def list_skills(base: Path | None = None) -> list[str]:
    base = base or skills_dir()
    return sorted(p.name for p in base.iterdir() if (p / "SKILL.md").exists()) if base.exists() else []


def remove_skill(name: str, base: Path | None = None) -> None:
    target = (base or skills_dir()) / name
    if target.parent == (base or skills_dir()) and target.exists():
        shutil.rmtree(target)


def skills_prompt(base: Path | None = None) -> str:
    chunks, total = [], 0
    for name in list_skills(base):
        text = ((base or skills_dir()) / name / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_SKILL_CHARS:
            text = text[:MAX_SKILL_CHARS] + "\n...(dipersingkat)..."
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        total += len(text)
        chunks.append(f"### {name}\n{text}")
    if not chunks:
        return ""
    return "\n--- PANDUAN SKILL TERPASANG ---\n" + "\n\n".join(chunks) + "\n--- AKHIR PANDUAN ---\n"
