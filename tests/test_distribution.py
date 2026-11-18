import base64
import json

import pytest

from vibemotion.config import Settings
from vibemotion.core import secrets
from vibemotion.core.updater import NoRelease, check_update, is_newer, parse_version


# ---------- rahasia ----------
def fake_enc(b: bytes) -> bytes:  # pengganti DPAPI untuk uji: bolak-balik, bukan enkripsi sungguhan
    return bytes(x ^ 0x5A for x in b)


def test_protect_roundtrip_and_prefix():
    tok = secrets.protect("sk-ant-RAHASIA", fake_enc, fake_enc)
    assert tok.startswith("dpapi:") and "RAHASIA" not in tok
    assert secrets.unprotect(tok, fake_enc) == ("sk-ant-RAHASIA", True)
    assert secrets.protect(tok, fake_enc, fake_enc) == tok  # idempoten
    assert secrets.protect("", fake_enc, fake_enc) == "" and secrets.unprotect("") == ("", True)
    assert secrets.unprotect("teks-lama") == ("teks-lama", True)  # migrasi dari versi lama


def test_protect_never_loses_key_when_encryption_fails():
    def boom(_b): raise OSError("DPAPI rusak")
    assert secrets.protect("AIzaX", boom, boom) == "AIzaX"
    # enkripsi "berhasil" tapi tidak bisa dibuka balik → jangan dipercaya
    assert secrets.protect("AIzaX", fake_enc, lambda b: b"lain") == "AIzaX"


def test_unprotect_failure_reports_not_ok():
    def boom(_b): raise OSError("akun lain")
    tok = "dpapi:" + base64.b64encode(b"x").decode()
    assert secrets.unprotect(tok, boom) == ("", False)
    assert secrets.unprotect("dpapi:%%%bukan-base64", fake_enc) == ("", False)


def test_non_windows_is_passthrough(monkeypatch):
    monkeypatch.setattr(secrets, "available", lambda: False)
    assert secrets.protect("abc") == "abc"
    assert secrets.unprotect("dpapi:AAAA") == ("", False)  # tidak bisa dibuka di OS lain


def test_settings_encrypts_on_disk_and_decrypts_on_load(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "protect", lambda t, *a: secrets.PREFIX + base64.b64encode(fake_enc(t.encode())).decode() if t else t)
    monkeypatch.setattr(secrets, "unprotect", lambda v, *a: ((fake_enc(base64.b64decode(v[6:])).decode(), True) if v.startswith("dpapi:") else (v, True)))
    f = tmp_path / "c.json"
    Settings(gemini_keys=["AIzaSECRET1", "AIzaSECRET2"], anthropic_key="sk-ant-SECRET", openai_key="sk-SECRET", fps=24).save(f)
    raw = f.read_text()
    assert "SECRET" not in raw and raw.count("dpapi:") == 4
    s = Settings.load(f)
    assert s.gemini_keys == ["AIzaSECRET1", "AIzaSECRET2"] and s.anthropic_key == "sk-ant-SECRET" and s.fps == 24
    assert s.secrets_lost is False


def test_settings_migrates_plaintext_config(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"anthropic_key": "sk-ant-LAMA", "gemini_keys": ["AIzaLAMA"]}))
    s = Settings.load(f)
    assert s.anthropic_key == "sk-ant-LAMA" and s.gemini_keys == ["AIzaLAMA"] and not s.secrets_lost


def test_settings_flags_unreadable_keys(tmp_path):
    f = tmp_path / "c.json"
    tok = "dpapi:" + base64.b64encode(b"zzz").decode()
    f.write_text(json.dumps({"anthropic_key": tok, "gemini_keys": [tok, "AIzaOK"], "openai_key": ""}))
    s = Settings.load(f)  # di Linux dpapi tidak bisa dibuka → hilang, tapi key lain selamat & ada penanda
    assert s.anthropic_key == "" and s.gemini_keys == ["AIzaOK"] and s.secrets_lost is True


def test_settings_roundtrip_defaults_untouched(tmp_path):
    f = tmp_path / "c.json"; Settings(provider="openai").save(f)
    s = Settings.load(f); assert s.provider == "openai" and s.update_url == "" and s.check_updates is True


# ---------- updater ----------
@pytest.mark.parametrize("text,exp", [("v1.2.3", (1, 2, 3)), ("0.9-alur-editor", (0, 9)), ("1.0", (1, 0)),
                                       ("", ()), ("beta", ()), ("V2", (2,))])
def test_parse_version(text, exp):
    assert parse_version(text) == exp


@pytest.mark.parametrize("latest,cur,newer", [("0.10", "0.9-alur-editor", True), ("0.9.1", "0.9", True),
                                               ("0.9", "0.9.0", False), ("v1.0.0", "0.9-x", True),
                                               ("0.8", "0.9", False), ("", "0.9", False), ("rilis", "0.9", False)])
def test_is_newer(latest, cur, newer):
    assert is_newer(latest, cur) is newer


class R:
    def __init__(self, status, data=None): self.status_code, self._d = status, data
    def json(self): return self._d
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")


class H:
    def __init__(self, *responses): self.r, self.urls = list(responses), []
    def get(self, url, **kw): self.urls.append(url); return self.r.pop(0)


def test_check_update_github_release():
    h = H(R(200, {"tag_name": "v0.10", "html_url": "https://github.com/o/r/releases/tag/v0.10", "body": "catatan"}))
    info = check_update("https://github.com/o/r", "0.9-alur-editor", h)
    assert info and info.version == "v0.10" and info.notes == "catatan" and "api.github.com/repos/o/r/releases/latest" in h.urls[0]
    assert check_update("https://github.com/o/r/", "0.10", H(R(200, {"tag_name": "v0.10"}))) is None  # sama
    with pytest.raises(NoRelease, match="Release"):  # 404: tidak ada Release (bukan "sudah terbaru")
        check_update("https://github.com/o/r.git", "0.1", H(R(404)))


def test_check_update_json_and_safety():
    h = H(R(200, {"version": "2.0", "url": "https://situs.example/unduh", "notes": "baru"}))
    assert check_update("https://situs.example/v.json", "1.0", h).url == "https://situs.example/unduh"
    evil = H(R(200, {"version": "2.0", "url": "javascript:alert(1)"}))
    assert check_update("https://situs.example/v.json", "1.0", evil).url == "https://situs.example/v.json"  # non-https ditolak
    for bad in ("http://x.com/v.json", "file:///etc/passwd", "", "ftp://x"):
        with pytest.raises(ValueError):
            check_update(bad, "1.0", H())
    with pytest.raises(RuntimeError):
        check_update("https://situs.example/v.json", "1.0", H(R(500)))
