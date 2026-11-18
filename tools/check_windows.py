"""Pemeriksaan di Windows SUNGGUHAN — hal yang tidak bisa diuji di Linux.

  python tools\\check_windows.py                                   # DPAPI + ikon
  python tools\\check_windows.py --exe dist\\VibeMotionNext\\VibeMotionNext.exe
  python tools\\check_windows.py --installer dist\\VibeMotionNext-Setup-0.10.exe
  python tools\\check_windows.py --repo https://github.com/pemilik/repo   # cek pembaruan ke GitHub nyata

Semua opsi boleh digabung. Kode keluar 0 = semua lolos. Installer dipasang ke folder sementara (per-pengguna) lalu dihapus.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results: list[tuple[str, str, str]] = []  # (status, nama, detail)


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append(("LOLOS" if ok else "GAGAL", name, "" if ok else detail))
    print(("  ✔ " if ok else "  ✘ ") + name + ("" if ok else f"  → {detail}"), flush=True)
    return ok


def skip(name: str, why: str) -> None:
    results.append(("LEWAT", name, why))
    print(f"  – {name}  (dilewati: {why})", flush=True)


def check_dpapi() -> None:
    print("\n[DPAPI]")
    from vibemotion.config import Settings
    from vibemotion.core import secrets
    if os.name != "nt":
        return skip("DPAPI", "bukan Windows")
    secret = "AIzaSy-UJI-RAHASIA-ünïcode-123"
    token = secrets.protect(secret)
    check("protect menghasilkan token dpapi:", token.startswith("dpapi:"), token[:30])
    check("plaintext tidak ada di token", secret not in token)
    check("unprotect mengembalikan nilai asli", secrets.unprotect(token) == (secret, True))
    raw = bytearray(__import__("base64").b64decode(token[6:]))
    raw[len(raw) // 2] ^= 0xFF
    tampered = "dpapi:" + __import__("base64").b64encode(bytes(raw)).decode()
    import logging
    logging.disable(logging.CRITICAL)  # peringatan "tidak bisa dibuka" di sini memang disengaja
    try:
        rejected = secrets.unprotect(tampered) == ("", False)
    finally:
        logging.disable(logging.NOTSET)
    check("token yang diubah ditolak (tidak crash)", rejected)
    check("dua enkripsi nilai sama berbeda (salt)", secrets.protect(secret) != token)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "config.json"
        Settings(gemini_keys=[secret, secret + "2"], anthropic_key="sk-ant-" + secret, openai_key="sk-" + secret).save(f)
        text = f.read_text(encoding="utf-8")
        check("config.json tidak memuat key polos", secret not in text and text.count("dpapi:") == 4)
        loaded = Settings.load(f)
        check("config dimuat kembali utuh", loaded.gemini_keys == [secret, secret + "2"] and loaded.anthropic_key == "sk-ant-" + secret
              and not loaded.secrets_lost)
        f.write_text(json.dumps({"anthropic_key": "sk-ant-LAMA"}), encoding="utf-8")
        check("migrasi config lama (teks biasa)", Settings.load(f).anthropic_key == "sk-ant-LAMA")


def check_icon() -> None:
    print("\n[Ikon]")
    from PIL import Image
    ico = ROOT / "assets" / "icon.ico"
    if not check("assets/icon.ico ada", ico.exists()):
        return
    sizes = {s[0] for s in Image.open(ico).ico.sizes()}
    check("ikon memuat ukuran 16/32/48/256", {16, 32, 48, 256} <= sizes, str(sorted(sizes)))


def run_selftest(exe: Path) -> bool:
    try:
        p = subprocess.run([str(exe), "--selftest"], timeout=180)
    except subprocess.TimeoutExpired:
        return check(f"selftest {exe.name}", False, "melebihi 180 detik (jendela macet?)")
    note = ""
    log = Path(os.environ.get("APPDATA", "")) / "VibeMotionNext" / "logs" / "selftest.txt"
    if log.exists():
        note = log.read_text(encoding="utf-8").strip()
    return check(f"selftest {exe.name} (kode keluar 0)", p.returncode == 0, f"kode {p.returncode}; {note}")


def check_exe(exe: Path) -> None:
    print(f"\n[EXE] {exe}")
    if os.name != "nt":
        return skip("exe", "bukan Windows")
    if not check("berkas .exe ada", exe.exists(), "belum dibangun — jalankan dulu: python tools\\build.py --skip-tests"):
        return
    from vibemotion import __version__
    ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                         f"(Get-Item '{exe}').VersionInfo | ConvertTo-Json"], capture_output=True, text=True)
    try:
        info = json.loads(ps.stdout)
        check("properti versi .exe terisi", info.get("ProductName") == "Vibe Motion Next" and __version__ in str(info.get("ProductVersion")),
              ps.stdout[:200])
    except ValueError:
        check("properti versi .exe terisi", False, ps.stderr[:200] or ps.stdout[:200])
    run_selftest(exe)


def check_installer(setup: Path) -> None:
    print(f"\n[Installer] {setup}")
    if os.name != "nt":
        return skip("installer", "bukan Windows")
    if not check("berkas installer ada", setup.exists(), "belum dibangun — jalankan: python tools\\build.py --skip-tests --installer (perlu Inno Setup)"):
        return
    appdata = Path(os.environ.get("APPDATA", "")) / "VibeMotionNext"
    appdata.mkdir(parents=True, exist_ok=True)
    marker = appdata / "_marker_uji_uninstall.txt"
    marker.write_text("data pengguna harus selamat setelah uninstall", encoding="utf-8")
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "Vibe Motion Next"
        log = Path(d) / "setup.log"
        p = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
                            f"/DIR={target}", f"/LOG={log}"], timeout=600)
        check("instalasi senyap sukses", p.returncode == 0, f"kode {p.returncode}; lihat {log}")
        exe = target / "VibeMotionNext.exe"
        if check("VibeMotionNext.exe terpasang", exe.exists()):
            check("ikon & data terbawa (_internal)", (target / "_internal").exists())
            run_selftest(exe)
        unins = next(iter(target.glob("unins*.exe")), None)
        if check("uninstaller tersedia", unins is not None) and unins:
            u = subprocess.run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=300)
            check("uninstall senyap sukses", u.returncode == 0, f"kode {u.returncode}")
            import time
            time.sleep(3)
            check("folder program terhapus", not exe.exists())
    check("data pengguna (AppData) selamat setelah uninstall", marker.exists())
    marker.unlink(missing_ok=True)


def check_update(repo: str) -> None:
    print(f"\n[Cek pembaruan] {repo}")
    from vibemotion.core.updater import NoRelease, check_update as cu
    try:
        newer = cu(repo, "0.0.1")
        check("rilis terbaru terbaca dari server nyata", newer is not None and bool(newer.version) and newer.url.startswith("https://"),
              repr(newer))
        print(f"     versi terbaru: {newer.version if newer else '-'}  {newer.url if newer else ''}")
        check("versi lokal 999.0 → tidak ada pembaruan", cu(repo, "999.0") is None)
    except NoRelease as e:
        check("repo punya Release", False, f"{e} Coba repo lain yang punya Release, mis. https://github.com/cli/cli")
    except Exception as e:  # noqa: BLE001
        check("panggilan ke server berhasil", False, f"{type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", type=Path)
    ap.add_argument("--installer", type=Path)
    ap.add_argument("--repo", help="URL repo GitHub yang punya minimal satu Release")
    a = ap.parse_args()
    from vibemotion import __version__
    print(f"Vibe Motion Next v{__version__} — pemeriksaan Windows ({sys.platform})")
    check_dpapi()
    check_icon()
    if a.exe:
        check_exe(a.exe)
    if a.installer:
        check_installer(a.installer)
    if a.repo:
        check_update(a.repo)
    fails = [r for r in results if r[0] == "GAGAL"]
    print(f"\nRingkasan: {sum(r[0]=='LOLOS' for r in results)} lolos, {len(fails)} gagal, {sum(r[0]=='LEWAT' for r in results)} dilewati")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
