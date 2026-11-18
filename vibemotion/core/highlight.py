"""Tokenizer ringan TS/TSX untuk syntax highlighting (murni, tanpa Tk)."""
from __future__ import annotations

import re

KEYWORDS = ("import|export|from|const|let|var|function|return|if|else|for|while|switch|case|break|continue|new|typeof|"
            "as|default|class|interface|type|extends|async|await|true|false|null|undefined|in|of|void")
_TOKEN = re.compile(
    r"""(?P<comment>//[^\n]*|/\*.*?\*/)
    |(?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)
    |(?P<number>\b\d+(?:\.\d+)?\b)
    |(?P<tag></?[A-Z][\w.]*|</?[a-z][\w-]*(?=[\s>/]))
    |(?P<keyword>\b(?:%s)\b)
    |(?P<func>\b[A-Za-z_$][\w$]*(?=\())""" % KEYWORDS,
    re.S | re.X,
)
MAX_CHARS = 200_000

# Warna untuk tema gelap
COLORS = {"comment": "#6b7a8f", "string": "#a5d6a7", "number": "#ffcc80", "tag": "#80cbc4",
          "keyword": "#c792ea", "func": "#82aaff"}


def tokenize(code: str) -> list[tuple[str, int, int]]:
    if len(code) > MAX_CHARS:
        return []
    return [(m.lastgroup, m.start(), m.end()) for m in _TOKEN.finditer(code)]
