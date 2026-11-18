"""Build lengkap: tes → ikon → info versi → PyInstaller → (opsional) zip portabel + installer.

Pemakaian:  python tools/build.py [--skip-tests] [--zip] [--installer]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def find_iscc() -> str | None:
    """Cari kompilator Inno Setup: PATH dulu, lalu lokasi instalasi standar (choco tidak selalu mengubah PATH)."""
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    roots = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]
    for root in filter(None, roots):
        for folder in ("Inno Setup 6", "Inno Setup 7", r"Programs\Inno Setup 6", r"Programs\Inno Setup 7"):
            cand = Path(root) / folder / "ISCC.exe"
            if cand.exists():
                return str(cand)
    return None


def run(cmd: list[str]) -> None:
    print("›", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--zip", action="store_true", help="buat zip portabel di dist/")
    ap.add_argument("--installer", action="store_true", help="bangun installer dengan Inno Setup (iscc)")
    args = ap.parse_args()

    from vibemotion import __version__
    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "-q"])
    run([sys.executable, "tools/make_icon.py"])
    run([sys.executable, "tools/make_version_info.py"])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "VibeMotionNext.spec"])

    out = ROOT / "dist" / "VibeMotionNext"
    exe = out / ("VibeMotionNext.exe" if sys.platform == "win32" else "VibeMotionNext")
    if not exe.exists():
        print("Build gagal: berkas utama tidak ditemukan", exe)
        return 1
    # pemeriksaan asap pada hasil bungkusan (butuh display; dilewati di server tanpa layar)
    print("› selftest", exe)
    res = subprocess.run([str(exe), "--selftest"], timeout=120)
    if res.returncode != 0:
        print("SELFTEST GAGAL (kode", res.returncode, ") — cek logs/selftest.txt di %APPDATA%\\VibeMotionNext")
        return res.returncode

    if args.zip:
        archive = shutil.make_archive(str(ROOT / "dist" / f"VibeMotionNext-{__version__}-portable"), "zip", out.parent, out.name)
        print("Portabel:", archive)
    if args.installer:
        iscc = find_iscc()
        if not iscc:
            print("GAGAL: --installer diminta tetapi iscc (Inno Setup) tidak ditemukan. Pasang dari jrsoftware.org / choco install innosetup.")
            return 2
        run([iscc, f"/DAppVersion={__version__.split('-')[0]}", "installer/VibeMotionNext.iss"])
        if not list((ROOT / "dist").glob("VibeMotionNext-Setup-*.exe")):
            print("GAGAL: iscc selesai tetapi installer tidak ada di dist/")
            return 3
    print("Selesai:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
