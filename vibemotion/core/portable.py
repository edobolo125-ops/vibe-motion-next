"""Ekspor/impor proyek sebagai .zip (cadangan & pindah komputer)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath

from .project import PLACEHOLDER_CODE, Project, VideoItem

FORMAT = "vibemotion-project/1"
MAX_ASSET_MB = 200


def export_project(project: Project, zip_path: Path) -> int:
    """Tulis zip: manifest + kode tiap video + aset. Kembalikan jumlah video."""
    manifest = {"format": FORMAT, "items": [
        {"id": i.id, "name": i.name, "width": i.width, "height": i.height, "fps": i.fps, "duration_sec": i.duration_sec,
         "music": i.music, "music_volume": i.music_volume, "voiceover": i.voiceover}
        for i in project.items]}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for i in project.items:
            z.writestr(f"compositions/{i.id}.tsx", i.code)
        if project.assets_dir.exists():
            for f in sorted(project.assets_dir.iterdir()):
                if f.is_file():
                    z.write(f, f"assets/{f.name}")
    return len(project.items)


def import_project(project: Project, zip_path: Path) -> list[VideoItem]:
    """Tambahkan video & aset dari zip sebagai item BARU (tidak menimpa yang ada)."""
    new: list[VideoItem] = []
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        if "manifest.json" not in names:
            raise ValueError("Bukan berkas proyek Vibe Motion (manifest.json tidak ada).")
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != FORMAT:
            raise ValueError("Format proyek tidak dikenali.")
        for m in manifest.get("items", []):
            member = f"compositions/{PurePosixPath(str(m.get('id', ''))).name}.tsx"
            code = z.read(member).decode("utf-8") if member in names else PLACEHOLDER_CODE
            opts = {k: m[k] for k in ("width", "height", "fps", "duration_sec", "music", "music_volume", "voiceover") if k in m}
            new.append(project.add(code, str(m.get("name", "Impor")), **opts))
        project.assets_dir.mkdir(parents=True, exist_ok=True)
        for info in z.infolist():
            p = PurePosixPath(info.filename)
            # hanya berkas langsung di assets/ — nama dibersihkan agar tidak bisa keluar folder (zip-slip)
            if len(p.parts) == 2 and p.parts[0] == "assets" and not info.is_dir() and p.name not in ("", ".", ".."):
                if info.file_size > MAX_ASSET_MB * 1024 * 1024:
                    continue
                (project.assets_dir / p.name).write_bytes(z.read(info))
    return new
