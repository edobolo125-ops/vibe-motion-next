"""Cari / ganti teks (murni, mengembalikan offset karakter)."""
from __future__ import annotations

import re


def _pattern(query: str, case: bool, regex: bool) -> re.Pattern:
    try:
        return re.compile(query if regex else re.escape(query), 0 if case else re.I)
    except re.error as e:
        raise ValueError(f"Pola regex tidak valid: {e}") from e


def find_all(text: str, query: str, case: bool = False, regex: bool = False) -> list[tuple[int, int]]:
    if not query:
        return []
    return [(m.start(), m.end()) for m in _pattern(query, case, regex).finditer(text) if m.end() > m.start()]


def next_match(spans: list[tuple[int, int]], pos: int, forward: bool = True) -> int | None:
    """Indeks span berikutnya/sebelumnya dari posisi kursor (melingkar). None bila kosong."""
    if not spans:
        return None
    if forward:
        return next((i for i, (s, _e) in enumerate(spans) if s >= pos), 0)
    prev = [i for i, (s, _e) in enumerate(spans) if s < pos]
    return prev[-1] if prev else len(spans) - 1


def replace_all(text: str, query: str, repl: str, case: bool = False, regex: bool = False) -> tuple[str, int]:
    if not query:
        return text, 0
    pat = _pattern(query, case, regex)
    count = len(find_all(text, query, case, regex))
    try:
        return pat.sub((lambda m: repl) if not regex else repl, text), count
    except (re.error, IndexError) as e:
        raise ValueError(f"Pengganti tidak valid: {e}") from e
