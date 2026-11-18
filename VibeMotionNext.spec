# -*- mode: python ; coding: utf-8 -*-
# Build:  python tools/build.py      (atau)  pyinstaller --noconfirm VibeMotionNext.spec
# Hasil:  dist/VibeMotionNext/VibeMotionNext(.exe)   (mode onedir: start cepat, lebih jarang dianggap virus
#         dibanding onefile, dan cocok dibungkus installer)
import os
from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")
datas = ctk_datas + [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]
icon = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None
version = "build/version_info.txt" if os.path.exists("build/version_info.txt") else None

a = Analysis(
    ["run.py"], pathex=["."], binaries=ctk_binaries, datas=datas,
    hiddenimports=ctk_hidden + ["PIL._tkinter_finder"],
    excludes=["pytest", "numpy", "matplotlib", "scipy", "pandas", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VibeMotionNext", console=False,
          icon=icon, version=version, upx=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VibeMotionNext")
