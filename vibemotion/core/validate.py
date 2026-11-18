"""Validasi kode TSX hasil AI sebelum masuk editor: statis + sintaks (esbuild) bila Node tersedia."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .proc import IS_WIN, find_tool

BUILTIN_PKGS = {"react", "react-dom", "remotion"}
_IMPORT = re.compile(r"""(?:import|export)\s[^;]*?from\s+["']([^"'.][^"']*)["']|import\s+["']([^"'.][^"']*)["']""")
_STATICFILE = re.compile(r"""staticFile\(\s*["']([^"']+)["']\s*\)""")
_EXPORT_OK = re.compile(r"\bexport\s+(?:const|function|class)\s+Remotion\b|export\s*\{[^}]*\bas\s+Remotion\b")
_BAD_CALLS = [
    (re.compile(r"\bsetTimeout\s*\("), "setTimeout tidak boleh dipakai; hitung animasi dari useCurrentFrame()."),
    (re.compile(r"\bsetInterval\s*\("), "setInterval tidak boleh dipakai; hitung animasi dari useCurrentFrame()."),
    (re.compile(r"\brequestAnimationFrame\s*\("), "requestAnimationFrame tidak boleh dipakai; pakai useCurrentFrame()."),
    (re.compile(r"\bMath\.random\s*\("), "Math.random() membuat render tidak konsisten; pakai random(\"seed\") dari remotion."),
    (re.compile(r"\btransition\s*:\s*[\"'`]"), "CSS transition tidak jalan saat render; pakai interpolate()/spring()."),
    (re.compile(r"\banimation\s*:\s*[\"'`]"), "CSS animation tidak jalan saat render; pakai interpolate()/spring()."),
]

_ESBUILD_JS = (
    "const e=require('esbuild');let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{try{"
    "e.transformSync(s,{loader:'tsx'});process.stdout.write('OK')}catch(err){"
    "process.stdout.write('ERR\\n'+((err.errors||[]).map(x=>(x.location?x.location.line+':'+x.location.column+' ':'')+x.text).join('\\n')||String(err)))}})"
)


@dataclass(frozen=True)
class Issue:
    kind: str  # syntax | export | package | asset | determinism
    message: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


def _pkg_name(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def _without_comments(code: str) -> str:
    """Buang komentar (// dan /* */) memakai tokenizer — tanda // di dalam string ("https://…") tidak ikut terbuang."""
    from .highlight import tokenize
    out, last = [], 0
    for kind, start, end in tokenize(code):
        if kind == "comment":
            out.append(code[last:start])
            last = end
    out.append(code[last:])
    return "".join(out)


def has_remotion_export(code: str) -> bool:
    """Apakah kode mengekspor komponen `Remotion` (yang dicari Root.tsx)?"""
    return bool(_EXPORT_OK.search(_without_comments(code)))


def static_checks(code: str, root: Path | None = None) -> list[Issue]:
    code = _without_comments(code)  # komentar tidak boleh memengaruhi pemeriksaan
    issues: list[Issue] = []
    if not _EXPORT_OK.search(code):
        issues.append(Issue("export", "Komponen harus diekspor sebagai `export const Remotion: React.FC = () => ...`."))
    nm = (Path(root) / "node_modules") if root else None
    seen: set[str] = set()
    for m in _IMPORT.finditer(code):
        pkg = _pkg_name(m.group(1) or m.group(2))
        if pkg in seen or pkg in BUILTIN_PKGS:
            continue
        seen.add(pkg)
        if nm is not None and nm.exists() and not (nm / pkg).exists():
            issues.append(Issue("package", f"Paket '{pkg}' tidak terpasang. Hapus penggunaannya atau pakai paket yang tersedia."))
    if root is not None:
        for rel in dict.fromkeys(_STATICFILE.findall(code)):
            if not (Path(root) / "public" / rel).exists():
                issues.append(Issue("asset", f"File aset '{rel}' tidak ada di public/. Pakai hanya aset yang tersedia."))
    for pattern, msg in _BAD_CALLS:
        if pattern.search(code):
            issues.append(Issue("determinism", msg))
    return issues


def syntax_check(root: Path, code: str, timeout: int = 30) -> Issue | None:
    """Kompilasi TSX dengan esbuild milik proyek. None = lolos / tidak bisa dicek (Node/esbuild tidak ada)."""
    node = find_tool("node")
    if not node or not (Path(root) / "node_modules" / "esbuild").exists():
        return None
    try:
        out = subprocess.run([node, "-e", _ESBUILD_JS], cwd=str(root), input=code, capture_output=True,
                             text=True, encoding="utf-8", timeout=timeout,
                             creationflags=0x08000000 if IS_WIN else 0)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or "").strip()
    if text.startswith("ERR"):
        return Issue("syntax", text[3:].strip()[:600] or "kesalahan sintaks")
    return None


def check_code(code: str, root: Path | None = None, run_syntax: bool = True) -> list[Issue]:
    issues = static_checks(code, root)
    if run_syntax and root is not None:
        syn = syntax_check(Path(root), code)
        if syn:
            issues.insert(0, syn)
    return issues


def issues_to_text(issues: list[Issue]) -> str:
    return "\n".join(f"- {i}" for i in issues)


__all__ = ["Issue", "check_code", "static_checks", "syntax_check", "issues_to_text", "json"]
