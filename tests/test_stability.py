import json
import logging
import sys
import threading

import pytest

from vibemotion.config import Settings
from vibemotion.core import logs
from vibemotion.core.errors import friendly_message
from vibemotion.core.fsutil import atomic_write
from vibemotion.core.project import Project


@pytest.mark.parametrize("raw,needle", [
    ('Claude 400: {"message":"Your credit balance is too low to access the Anthropic API"}', "Saldo kredit"),
    ('Gemini 400: {"reason": "API_KEY_INVALID"}', "API key tidak valid"),
    ("Gemini 404: This model models/gemini-2.5-flash is no longer available to new users", "Refresh"),
    ("Semua key/percobaan gagal: server 503", "sibuk"),
    ("Gemini 429: RESOURCE_EXHAUSTED", "kuota"),
    ("HTTPSConnectionPool: Max retries exceeded with url", "internet"),
    ("Node.js tidak ditemukan. Pasang dari https://nodejs.org", "Node.js belum terpasang"),
    ("PermissionError: [WinError 32] being used by another process", "sedang dipakai"),
    ("Balasan AI bukan komponen Remotion yang valid.", "kode video"),
])
def test_friendly_messages_id(raw, needle):
    msg = friendly_message(raw, "id")
    assert needle in msg and "Detail teknis" in msg


def test_friendly_english_and_fallback():
    assert "Quota" in friendly_message("429 quota", "en") and "Detail:" in friendly_message("429 quota", "en")
    assert friendly_message(ValueError("aneh sekali"), "id") == "ValueError: aneh sekali"
    assert friendly_message("", "id") == "Kesalahan tidak diketahui"
    assert len(friendly_message("503 " + "x" * 5000, "id")) < 700  # detail dibatasi


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path):
    f = tmp_path / "a" / "b.txt"
    atomic_write(f, "satu"); atomic_write(f, "dua")
    assert f.read_text() == "dua" and not list(f.parent.glob("*.tmp"))


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    f = tmp_path / "k.txt"; atomic_write(f, "lama")
    monkeypatch.setattr("os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk penuh")))
    with pytest.raises(OSError):
        atomic_write(f, "baru")
    assert f.read_text() == "lama"


def test_settings_tolerates_bad_types(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"fps": "60", "duration_sec": "abc", "gemini_keys": "bukan-list",
                             "provider": 5, "concurrency": True, "ratio": "9:16"}))
    s = Settings.load(f)
    assert s.fps == 60 and s.duration_sec == 10.0 and s.gemini_keys == [] and s.provider == "gemini"
    assert s.concurrency == 0 and s.ratio == "9:16"
    f.write_text("[1,2]"); assert Settings.load(f).fps == 30
    f.write_text("{rusak"); assert Settings.load(f).fps == 30


def test_project_recovers_from_corrupt_state(tmp_path):
    p = Project(tmp_path)
    p.add("export const Remotion = () => null;", "Satu"); p.add(name="Dua"); p.save()
    (tmp_path / "vibemotion.json").write_text("{bukan json")
    q = Project(tmp_path); q.load()
    assert [i.id for i in q.items] == ["scene_001", "scene_002"]
    assert q.items[0].code.startswith("export const Remotion")
    assert (tmp_path / "vibemotion.corrupt.json").exists()


def test_project_skips_bad_entries_and_never_empty(tmp_path):
    p = Project(tmp_path); p.add(name="ok"); p.save()
    (tmp_path / "vibemotion.json").write_text(json.dumps([{"id": "scene_001", "name": "ok", "zzz": 1}, {"tanpa": "id"}, 5]))
    q = Project(tmp_path); q.load()
    assert [i.id for i in q.items] == ["scene_001"]
    (tmp_path / "vibemotion.json").write_text("[]")
    r = Project(tmp_path); r.load(); assert len(r.items) == 1


def test_logging_captures_unhandled_and_thread_exceptions(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "_configured", False)
    logger = logging.getLogger("vibemotion")
    old_hooks = (sys.excepthook, threading.excepthook, list(logger.handlers))
    try:
        logs.setup_logging(directory=tmp_path)
        t = threading.Thread(target=lambda: 1 / 0, name="pekerja"); t.start(); t.join()
        sys.excepthook(ValueError, ValueError("boom"), None)
        for h in logger.handlers: h.flush()
        text = (tmp_path / "app.log").read_text(encoding="utf-8")
        assert "=== start ===" in text and "pekerja" in text and "ZeroDivisionError" in text and "boom" in text
    finally:
        sys.excepthook, threading.excepthook = old_hooks[0], old_hooks[1]
        logger.handlers[:] = old_hooks[2]


def test_diagnostics_has_no_secrets():
    from vibemotion.core.diagnostics import diagnostics_text
    s = Settings(gemini_keys=["AIzaSECRET"], anthropic_key="sk-ant-SECRET", openai_key="sk-SECRET")
    out = diagnostics_text(s)
    assert "SECRET" not in out and "gemini:1" in out and "Vibe Motion Next v" in out
