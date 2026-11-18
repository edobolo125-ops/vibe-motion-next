"""Titik masuk (juga dipakai PyInstaller)."""
import multiprocessing
import os
import sys

# Build --noconsole: stdout/stderr bernilai None; arahkan ke devnull supaya library yang mencetak tidak crash.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

from vibemotion.app import main  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
