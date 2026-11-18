"""Cek pembaruan: repo GitHub (rilis terbaru) atau JSON {"version","url","notes"}. Hanya https."""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

_GITHUB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


class NoRelease(LookupError):
    """Repo ada tetapi tidak punya Release (tag saja tidak cukup), atau repo tidak ditemukan / privat."""


class UpdateError(RuntimeError):
    """Pembaruan otomatis gagal atau ditolak karena alasan keamanan."""


# Installer HANYA boleh diunduh dari host GitHub rilis & dengan nama berpola — apa pun di luar itu ditolak.
ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
ASSET_RE = re.compile(r"^VibeMotionNext-Setup-[\w.\-]+\.exe$")
MAX_INSTALLER_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    notes: str = ""
    asset_url: str = ""      # URL installer (hanya dari rilis GitHub)
    asset_name: str = ""
    asset_sha256: str = ""   # dari digest GitHub bila tersedia; kosong = tidak bisa diverifikasi
    asset_size: int = 0


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' → (1,2,3); '0.9-alur-editor' → (0,9). Tanpa angka → ()."""
    head = re.split(r"[-+ ]", str(text).strip().lstrip("vV"), maxsplit=1)[0]
    nums = re.findall(r"\d+", head)
    return tuple(int(n) for n in nums)


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    if not a:
        return False
    width = max(len(a), len(b))
    pad = lambda t: t + (0,) * (width - len(t))  # noqa: E731
    return pad(a) > pad(b)


def check_update(source: str, current: str, http: requests.Session | None = None, timeout: int = 10) -> UpdateInfo | None:
    """UpdateInfo bila ada versi lebih baru, selain itu None. Lempar ValueError untuk alamat tidak valid."""
    source = (source or "").strip()
    if not source.startswith("https://"):
        raise ValueError("Alamat pembaruan harus diawali https://")
    http = http or requests.Session()
    gh = _GITHUB.match(source)
    if gh:
        r = http.get(f"https://api.github.com/repos/{gh.group(1)}/{gh.group(2)}/releases/latest", timeout=timeout,
                     headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            raise NoRelease("Repo tidak ditemukan, privat, atau belum punya Release di GitHub "
                            "(tag saja tidak cukup — buat Release di halaman Releases repo).")
        r.raise_for_status()
        data = r.json()
        version, page = str(data.get("tag_name", "")), str(data.get("html_url", source))
        notes = str(data.get("body") or "")[:600]
        asset = _pick_asset(data.get("assets") or [])
    else:
        r = http.get(source, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        version, page, notes = str(data.get("version", "")), str(data.get("url", source)), str(data.get("notes", ""))[:600]
        asset = {}
    if not page.startswith("https://"):
        page = source  # jangan pernah membuka tautan non-https dari data eksternal
    if not is_newer(version, current):
        return None
    return UpdateInfo(version, page, notes, **asset)


def host_allowed(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and (u.hostname or "").lower() in ALLOWED_HOSTS


def _pick_asset(assets: list) -> dict:
    """Pilih installer VibeMotionNext-Setup-*.exe dari daftar aset rilis; {} bila tidak ada/tidak aman."""
    for a in assets:
        try:
            name, url = str(a["name"]), str(a["browser_download_url"])
        except (KeyError, TypeError):
            continue
        if ASSET_RE.match(name) and host_allowed(url):
            digest = str(a.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            return {"asset_url": url, "asset_name": name, "asset_sha256": sha if re.fullmatch(r"[0-9a-f]{64}", sha) else "",
                    "asset_size": int(a.get("size") or 0)}
    return {}


def can_self_update() -> bool:
    """Hanya aplikasi terbungkus (.exe) di Windows yang memperbarui dirinya; versi `python run.py` cukup membuka halaman."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def download_installer(info: UpdateInfo, dest_dir: Path, http: requests.Session | None = None,
                       on_progress: Callable[[int, int], None] = lambda done, total: None,
                       timeout: int = 30) -> tuple[Path, bool]:
    """Unduh installer ke dest_dir. Kembalikan (path, terverifikasi). Menolak host/nama/ukuran/checksum yang salah."""
    if not info.asset_url or not host_allowed(info.asset_url):
        raise UpdateError("Alamat installer tidak diizinkan.")
    if not ASSET_RE.match(info.asset_name):
        raise UpdateError("Nama installer tidak valid.")
    http = http or requests.Session()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target, part = dest_dir / info.asset_name, dest_dir / (info.asset_name + ".part")
    sha = hashlib.sha256()
    done = 0
    r = http.get(info.asset_url, stream=True, timeout=timeout, allow_redirects=True)
    try:
        r.raise_for_status()
        if not host_allowed(str(getattr(r, "url", info.asset_url))):  # redirect ke host lain ditolak
            raise UpdateError("Pengalihan ke alamat yang tidak diizinkan.")
        total = int(r.headers.get("Content-Length") or info.asset_size or 0)
        if total > MAX_INSTALLER_BYTES:
            raise UpdateError("Ukuran installer melebihi batas.")
        with open(part, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if not chunk:
                    continue
                done += len(chunk)
                if done > MAX_INSTALLER_BYTES:
                    raise UpdateError("Ukuran installer melebihi batas.")
                sha.update(chunk)
                f.write(chunk)
                on_progress(done, total)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        close = getattr(r, "close", None)
        if close:
            close()
    if done == 0:
        part.unlink(missing_ok=True)
        raise UpdateError("Unduhan kosong.")
    if info.asset_sha256 and sha.hexdigest() != info.asset_sha256:
        part.unlink(missing_ok=True)
        raise UpdateError("Checksum SHA-256 tidak cocok — berkas dibuang demi keamanan.")
    part.replace(target)
    return target, bool(info.asset_sha256)


def launch_installer(path: Path, runner: Callable = subprocess.Popen) -> None:
    """Jalankan installer senyap (menutup aplikasi lama, memasang di atasnya). Pemanggil harus keluar sesudahnya."""
    if not ASSET_RE.match(Path(path).name):
        raise UpdateError("Nama installer tidak valid.")
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if sys.platform == "win32" else 0
    runner([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"], close_fds=True, creationflags=flags)
