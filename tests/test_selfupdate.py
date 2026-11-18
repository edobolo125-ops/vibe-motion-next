import hashlib
from pathlib import Path

import pytest

from vibemotion.core import updater
from vibemotion.core.updater import (UpdateError, UpdateInfo, check_update, download_installer, host_allowed,
                                     launch_installer)

DATA = b"MZ" + b"installer-bytes" * 5000
SHA = hashlib.sha256(DATA).hexdigest()
URL = "https://github.com/o/r/releases/download/v0.14/VibeMotionNext-Setup-0.14.exe"


def info(**kw):
    base = dict(version="v0.14", url="https://github.com/o/r/releases/tag/v0.14", asset_url=URL,
                asset_name="VibeMotionNext-Setup-0.14.exe", asset_sha256=SHA, asset_size=len(DATA))
    base.update(kw)
    return UpdateInfo(**base)


class Resp:
    def __init__(self, data=DATA, url=URL, status=200, length=None, fail_after=None):
        self.data, self.url, self.status_code, self.closed = data, url, status, False
        self.headers = {"Content-Length": str(len(data) if length is None else length)}
        self.fail_after = fail_after
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.data), chunk_size):
            if self.fail_after is not None and i >= self.fail_after: raise ConnectionError("putus")
            yield self.data[i:i + chunk_size]
    def close(self): self.closed = True


class Http:
    def __init__(self, resp): self.resp, self.calls = resp, []
    def get(self, url, **kw): self.calls.append((url, kw)); return self.resp


# ---------- pemilihan aset dari rilis ----------
def release(assets):
    class R:
        status_code = 200
        def json(self): return {"tag_name": "v0.14", "html_url": "https://github.com/o/r/releases/tag/v0.14", "body": "n", "assets": assets}
        def raise_for_status(self): pass
    class H:
        def get(self, url, **kw): return R()
    return H()


def test_check_update_picks_installer_and_digest():
    good = {"name": "VibeMotionNext-Setup-0.14.exe", "browser_download_url": URL, "size": 1234, "digest": f"sha256:{SHA.upper()}"}
    zip_ = {"name": "VibeMotionNext-0.14-portable.zip", "browser_download_url": "https://github.com/o/r/releases/download/v0.14/x.zip"}
    i = check_update("https://github.com/o/r", "0.13", release([zip_, good]))
    assert (i.asset_name, i.asset_url, i.asset_sha256, i.asset_size) == ("VibeMotionNext-Setup-0.14.exe", URL, SHA, 1234)


@pytest.mark.parametrize("asset", [
    {"name": "VibeMotionNext-Setup-0.14.exe", "browser_download_url": "https://evil.example/VibeMotionNext-Setup-0.14.exe"},
    {"name": "VibeMotionNext-Setup-0.14.exe", "browser_download_url": "http://github.com/o/r/VibeMotionNext-Setup-0.14.exe"},
    {"name": "malware.exe", "browser_download_url": URL},
    {"name": "VibeMotionNext-Setup-0.14.exe.bat", "browser_download_url": URL},
    {"name": "../VibeMotionNext-Setup-0.14.exe", "browser_download_url": URL},
    {"name": "VibeMotionNext-Setup-0.14.exe"},  # tanpa url
])
def test_unsafe_assets_are_ignored(asset):
    i = check_update("https://github.com/o/r", "0.13", release([asset]))
    assert i is not None and i.asset_url == "" and i.asset_name == ""  # pembaruan tetap ditawarkan, tapi tanpa unduhan otomatis


def test_bad_digest_format_is_dropped():
    a = {"name": "VibeMotionNext-Setup-0.14.exe", "browser_download_url": URL, "digest": "sha256:zzz"}
    assert check_update("https://github.com/o/r", "0.13", release([a])).asset_sha256 == ""
    b = {"name": "VibeMotionNext-Setup-0.14.exe", "browser_download_url": URL, "digest": "md5:abc"}
    assert check_update("https://github.com/o/r", "0.13", release([b])).asset_sha256 == ""


def test_json_source_has_no_asset():
    class R:
        status_code = 200
        def json(self): return {"version": "2.0", "url": "https://x.example/d"}
        def raise_for_status(self): pass
    class H:
        def get(self, *a, **k): return R()
    assert check_update("https://x.example/v.json", "1.0", H()).asset_url == ""  # JSON bebas tidak boleh memicu eksekusi


@pytest.mark.parametrize("url,ok", [("https://github.com/x", True), ("https://objects.githubusercontent.com/a", True),
                                     ("https://release-assets.githubusercontent.com/a", True), ("http://github.com/x", False),
                                     ("https://github.com.evil.io/x", False), ("https://evilgithub.com/x", False),
                                     ("https://user@evil.io/github.com", False), ("ftp://github.com/x", False), ("", False)])
def test_host_allowlist(url, ok):
    assert host_allowed(url) is ok


# ---------- unduh + verifikasi ----------
def test_download_ok_verified_and_progress(tmp_path):
    seen = []
    path, verified = download_installer(info(), tmp_path, Http(Resp()), lambda d, t: seen.append((d, t)))
    assert verified and path.read_bytes() == DATA and path.name == "VibeMotionNext-Setup-0.14.exe"
    assert seen[-1] == (len(DATA), len(DATA)) and not list(tmp_path.glob("*.part"))


def test_download_without_checksum_is_unverified(tmp_path):
    path, verified = download_installer(info(asset_sha256=""), tmp_path, Http(Resp()))
    assert path.exists() and verified is False


def test_checksum_mismatch_deletes_file(tmp_path):
    with pytest.raises(UpdateError, match="Checksum"):
        download_installer(info(asset_sha256="0" * 64), tmp_path, Http(Resp()))
    assert list(tmp_path.iterdir()) == []  # tidak ada sisa berkas yang bisa terpasang tak sengaja


@pytest.mark.parametrize("kw", [dict(asset_url="https://evil.example/x.exe"), dict(asset_url=""), dict(asset_name="x.exe"),
                                 dict(asset_name="../VibeMotionNext-Setup-1.exe")])
def test_download_rejects_bad_inputs_without_network(tmp_path, kw):
    h = Http(Resp())
    with pytest.raises(UpdateError):
        download_installer(info(**kw), tmp_path, h)
    assert h.calls == []


def test_redirect_to_other_host_rejected(tmp_path):
    with pytest.raises(UpdateError, match="Pengalihan"):
        download_installer(info(), tmp_path, Http(Resp(url="https://evil.example/VibeMotionNext-Setup-0.14.exe")))
    assert list(tmp_path.iterdir()) == []


def test_size_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "MAX_INSTALLER_BYTES", 1000)
    with pytest.raises(UpdateError, match="batas"):   # dari header
        download_installer(info(), tmp_path, Http(Resp()))
    with pytest.raises(UpdateError, match="batas"):   # header berbohong (0) tapi isi besar
        download_installer(info(asset_size=0), tmp_path, Http(Resp(length=0)))
    assert list(tmp_path.iterdir()) == []


def test_network_failure_midway_cleans_up_and_closes(tmp_path):
    r = Resp(fail_after=65536)
    with pytest.raises(ConnectionError):
        download_installer(info(), tmp_path, Http(r))
    assert list(tmp_path.iterdir()) == [] and r.closed
    with pytest.raises(UpdateError, match="kosong"):
        download_installer(info(), tmp_path, Http(Resp(data=b"")))
    with pytest.raises(RuntimeError):
        download_installer(info(), tmp_path, Http(Resp(status=404)))


# ---------- menjalankan installer ----------
def test_launch_installer_args_and_name_guard(tmp_path):
    calls = []
    launch_installer(tmp_path / "VibeMotionNext-Setup-0.14.exe", lambda cmd, **kw: calls.append((cmd, kw)))
    cmd, kw = calls[0]
    assert cmd[0].endswith("VibeMotionNext-Setup-0.14.exe") and cmd[1:] == ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
    assert kw["close_fds"] is True
    with pytest.raises(UpdateError):
        launch_installer(tmp_path / "calc.exe", lambda *a, **k: calls.append(1))
    assert len(calls) == 1


def test_can_self_update_only_when_frozen_on_windows(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32"); monkeypatch.delattr(updater.sys, "frozen", raising=False)
    assert updater.can_self_update() is False
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False); assert updater.can_self_update() is True
    monkeypatch.setattr(updater.sys, "platform", "linux"); assert updater.can_self_update() is False
