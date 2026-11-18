"""Utilitas murni (tanpa I/O) untuk kode TSX dan durasi — mudah diuji."""
from __future__ import annotations

import re

REACT_IMPORT = 'import React from "react";'
_FENCE = re.compile(r"```(?:tsx|typescript|ts|jsx|javascript|js)?\s*\n(.*?)```", re.S | re.I)
_REACT_IMPORT_RE = re.compile(r"^\s*import\s+(?:\*\s+as\s+)?React\b", re.M)
_NAMED_EXPORT = re.compile(r"\bexport\s+(?:const|function|class)\s+Remotion\b")
_DEFAULT_EXPORT = re.compile(r"\bexport\s+default\s+(?:function\s+|class\s+)?([A-Za-z_$][\w$]*)")


def clean_code_output(raw: str) -> str:
    """Ambil kode TSX dari balasan AI: buang pagar markdown dan teks pembuka/penutup."""
    text = raw.strip()
    blocks = _FENCE.findall(text)
    if blocks:
        text = max(blocks, key=len).strip()
    else:
        text = re.sub(r"^```\w*\s*|\s*```$", "", text).strip()
        m = re.search(r"^(import\s|export\s|const\s|//|/\*)", text, re.M)
        if m and m.start() > 0:
            text = text[m.start():]
    return ensure_react_import(ensure_remotion_export(text)) + "\n"


def ensure_react_import(code: str) -> str:
    if _REACT_IMPORT_RE.search(code):
        return code
    return f"{REACT_IMPORT}\n{code}"


def ensure_remotion_export(code: str) -> str:
    """Root.tsx mengimpor `{ Remotion }`; pastikan ekspor itu ada."""
    if _NAMED_EXPORT.search(code) or re.search(r"export\s*\{[^}]*\bas\s+Remotion\b", code):
        return code
    m = _DEFAULT_EXPORT.search(code)
    if m:
        return f"{code.rstrip()}\n\nexport {{ {m.group(1)} as Remotion }};"
    return code


def looks_like_component(code: str) -> bool:
    return bool(_NAMED_EXPORT.search(code) or _DEFAULT_EXPORT.search(code) or "as Remotion" in code)


_DURATION = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-z]*)")


def parse_duration_to_seconds(text: str, default: float = 10.0) -> float:
    """'30', '30s', '1.5 menit', '2m', '1m30s' → detik."""
    t = (text or "").strip().lower()
    if not t:
        return default
    total, found = 0.0, False
    for num, unit in _DURATION.findall(t):
        value = float(num.replace(",", "."))
        found = True
        if unit in ("m", "min", "mnt", "menit", "minute", "minutes"):
            total += value * 60
        elif unit in ("h", "j", "jam", "hour", "hours"):
            total += value * 3600
        else:
            total += value
    return total if found and total > 0 else default


def seconds_to_frames(seconds: float, fps: int) -> int:
    return max(1, round(seconds * fps))


def safe_filename(name: str, fallback: str = "video") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned or fallback
