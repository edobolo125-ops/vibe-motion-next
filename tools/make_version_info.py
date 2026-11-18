"""Buat berkas versi untuk PyInstaller (properti .exe di Windows: Detail → versi produk)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from vibemotion import __version__  # noqa: E402

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=({a}, {b}, {c}, 0), prodvers=({a}, {b}, {c}, 0), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Vibe Motion'),
      StringStruct('FileDescription', 'Vibe Motion Next - AI motion graphic generator for Remotion'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'VibeMotionNext'),
      StringStruct('OriginalFilename', 'VibeMotionNext.exe'),
      StringStruct('ProductName', 'Vibe Motion Next'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def numeric(version: str) -> tuple[int, int, int]:
    nums = [int(n) for n in re.findall(r"\d+", re.split(r"[-+ ]", version, maxsplit=1)[0])][:3]
    return tuple(nums + [0] * (3 - len(nums)))  # type: ignore[return-value]


def render(version: str = __version__) -> str:
    a, b, c = numeric(version)
    return TEMPLATE.format(a=a, b=b, c=c, ver=version.replace("'", ""))


def main() -> Path:
    out = ROOT / "build" / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main())
