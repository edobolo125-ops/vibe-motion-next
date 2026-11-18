"""Menguji kode ctypes DPAPI di secrets._dpapi dengan SIMULASI API Win32 (bukan Windows sungguhan).

Yang divalidasi: tata letak struct DATA_BLOB, urutan argumen CryptProtectData/CryptUnprotectData, pembacaan buffer
keluaran, pembebasan memori (LocalFree), dan penanganan kegagalan. Yang TIDAK bisa divalidasi di sini: perilaku
enkripsi Windows itu sendiri — itu diuji oleh tools/check_windows.py di Windows."""
import ctypes
from ctypes import wintypes

import pytest

from vibemotion.core import secrets


class FakeWin32:
    """Meniru crypt32/kernel32: memeriksa argumen persis seperti kontrak Win32."""

    def __init__(self, fail=False, key=0x5A):
        self.fail, self.key = fail, key
        self.keep, self.freed, self.calls = [], [], []

        def cp(pin, descr, entropy, reserved, prompt, flags, pout):
            return self._run("protect", pin, descr, entropy, reserved, prompt, flags, pout)

        def cu(pin, pdescr, entropy, reserved, prompt, flags, pout):
            return self._run("unprotect", pin, pdescr, entropy, reserved, prompt, flags, pout)

        class Crypt32:
            CryptProtectData, CryptUnprotectData = staticmethod(cp), staticmethod(cu)

        class Kernel32:
            class LocalFree:  # menerima atribut argtypes/restype seperti fungsi ctypes sungguhan
                argtypes = restype = None

                def __new__(cls, ptr):
                    outer.freed.append(ptr.value if hasattr(ptr, "value") else ptr)
                    return None

        outer = self
        self.crypt32, self.kernel32 = Crypt32, Kernel32

    def _run(self, name, pin, a2, entropy, reserved, prompt, flags, pout):
        self.calls.append(name)
        assert entropy is None and reserved is None and prompt is None and flags == 0  # argumen opsional kosong
        if self.fail:
            return 0
        blob_in, blob_out = pin._obj, pout._obj  # byref → struct asli
        assert type(blob_in).__name__ == "DATA_BLOB" and ctypes.sizeof(blob_in) == (16 if ctypes.sizeof(ctypes.c_void_p) == 8 else 8)
        data = ctypes.string_at(blob_in.pbData, blob_in.cbData)
        out = bytes(b ^ self.key for b in data)
        buf = ctypes.create_string_buffer(out, len(out))
        self.keep.append(buf)
        blob_out.cbData = len(out)
        blob_out.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
        return 1


@pytest.fixture
def win32(monkeypatch):
    fake = FakeWin32()
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"crypt32": fake.crypt32, "kernel32": fake.kernel32}), raising=False)
    monkeypatch.setattr(ctypes, "GetLastError", lambda: 1234, raising=False)
    monkeypatch.setattr(secrets, "available", lambda: True)
    return fake


def test_wintypes_available():
    # Catatan: di Linux wintypes.DWORD = c_ulong (8 byte), di Windows 4 byte. Tata letak DATA_BLOB sebenarnya
    # (4 + 4 padding + 8 = 16 byte pada x64) hanya bisa dibuktikan di Windows → tools/check_windows.py.
    assert wintypes.DWORD


def test_dpapi_call_sequence_and_roundtrip(win32):
    blob = secrets._dpapi(b"AIzaSy-rahasia", True)
    assert blob != b"AIzaSy-rahasia" and win32.calls == ["protect"]
    assert secrets._dpapi(blob, False) == b"AIzaSy-rahasia" and win32.calls == ["protect", "unprotect"]
    assert len(win32.freed) == 2  # memori keluaran selalu dibebaskan


def test_protect_unprotect_through_real_ctypes_path(win32):
    tok = secrets.protect("sk-ant-RAHASIA-ünïcode")
    assert tok.startswith("dpapi:") and "RAHASIA" not in tok
    assert secrets.unprotect(tok) == ("sk-ant-RAHASIA-ünïcode", True)


def test_empty_and_large_payloads(win32):
    assert secrets._dpapi(b"", True) == b""  # data kosong tidak crash
    big = bytes(range(256)) * 400
    assert secrets._dpapi(secrets._dpapi(big, True), False) == big


def test_win32_failure_becomes_oserror_and_protect_falls_back(monkeypatch):
    fake = FakeWin32(fail=True)
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"crypt32": fake.crypt32, "kernel32": fake.kernel32}), raising=False)
    monkeypatch.setattr(ctypes, "GetLastError", lambda: 13, raising=False)
    monkeypatch.setattr(secrets, "available", lambda: True)
    with pytest.raises(OSError, match="13"):
        secrets._dpapi(b"x", True)
    assert secrets.protect("AIzaX") == "AIzaX"  # key tidak hilang
    assert secrets.unprotect("dpapi:AAAA") == ("", False)
