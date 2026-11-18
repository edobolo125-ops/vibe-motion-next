"""Penyimpanan rahasia (API key) terenkripsi.

Windows: DPAPI (CryptProtectData) — terikat ke akun Windows pengguna; tanpa dependensi tambahan.
Lainnya: teks biasa (tidak ada penyimpan kunci bawaan yang portabel tanpa pustaka tambahan).
Aman terhadap kegagalan: bila enkripsi gagal atau hasilnya tidak bisa dibuka kembali, nilai disimpan apa adanya
supaya key pengguna tidak pernah hilang.
"""
from __future__ import annotations

import base64
import logging
import os

PREFIX = "dpapi:"
log = logging.getLogger("vibemotion.secrets")


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    # (pDataIn, szDescr/ppszDescr, pEntropy, pvReserved, pPrompt, dwFlags, pDataOut)
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise OSError(f"DPAPI gagal (kode {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def available() -> bool:
    return os.name == "nt"


def protect(text: str, _encrypt=None, _decrypt=None) -> str:
    """Enkripsi untuk disimpan. `_encrypt/_decrypt` hanya untuk pengujian."""
    if not text or text.startswith(PREFIX):
        return text
    enc = _encrypt or (lambda b: _dpapi(b, True))
    dec = _decrypt or (lambda b: _dpapi(b, False))
    if _encrypt is None and not available():
        return text
    try:
        token = PREFIX + base64.b64encode(enc(text.encode("utf-8"))).decode("ascii")
        if dec(base64.b64decode(token[len(PREFIX):])).decode("utf-8") != text:  # uji balik sebelum dipercaya
            raise ValueError("verifikasi enkripsi gagal")
        return token
    except Exception as e:  # noqa: BLE001
        log.warning("enkripsi key gagal, disimpan apa adanya: %s", e)
        return text


def unprotect(value: str, _decrypt=None) -> tuple[str, bool]:
    """(teks, berhasil). Nilai tanpa awalan dianggap teks biasa (migrasi dari versi lama)."""
    if not value or not value.startswith(PREFIX):
        return value, True
    dec = _decrypt or (lambda b: _dpapi(b, False))
    if _decrypt is None and not available():
        return "", False
    try:
        return dec(base64.b64decode(value[len(PREFIX):])).decode("utf-8"), True
    except Exception as e:  # noqa: BLE001 — akun/komputer berbeda, data rusak
        log.warning("key terenkripsi tidak bisa dibuka: %s", e)
        return "", False
