import json
import time
import zipfile
from pathlib import Path

import pytest

from vibemotion.core.highlight import tokenize
from vibemotion.core.history import History
from vibemotion.core.portable import export_project, import_project
from vibemotion.core.presets import RENDER_PRESETS, apply_preset
from vibemotion.core.project import Project
from vibemotion.core.render import RenderOptions, build_command
from vibemotion.core.textsearch import find_all, next_match, replace_all
from vibemotion.core.thumbs import existing_thumb, make_thumbs, thumb_path


# ---------- riwayat ----------
def test_history_snapshot_order_dedupe_restore(tmp_path):
    h = History(tmp_path)
    assert h.list("scene_001") == []
    a = h.snapshot("scene_001", "kode A", "manual")
    assert h.snapshot("scene_001", "kode A", "manual") is None  # sama dengan terbaru
    b = h.snapshot("scene_001", "kode B", "AI edit")
    entries = h.list("scene_001")
    assert [e.label for e in entries] == ["AI edit", "manual"] and entries[0].id == b.id
    assert h.read("scene_001", a.id) == "kode A" and h.read("scene_001", b.id) == "kode B"
    assert h.snapshot("scene_001", "kode A", "balik") is not None  # A lagi setelah B → versi baru
    assert h.list("scene_002") == []


def test_history_limit_unique_ids_and_traversal(tmp_path):
    h = History(tmp_path, limit=5)
    for i in range(12):
        h.snapshot("v", f"kode {i}", "x")
    entries = h.list("v")
    assert len(entries) == 5 and h.read("v", entries[0].id) == "kode 11" and len({e.id for e in entries}) == 5
    (tmp_path / "rahasia.tsx").write_text("RAHASIA")
    with pytest.raises(OSError):
        h.read("v", "../../rahasia.tsx")
    h.snapshot("../../evil", "x", "../lbl")  # id & label dibersihkan, tetap di dalam .vm_history
    assert not (tmp_path.parent / "evil").exists()
    assert all(p.is_relative_to(tmp_path / ".vm_history") for p in (tmp_path / ".vm_history").rglob("*.tsx"))


def test_project_snapshot_helper(tmp_path):
    p = Project(tmp_path); it = p.add(name="A")
    it.code = "x1"; assert p.snapshot(it.id, "satu")
    it.code = "x2"; assert p.snapshot(it.id, "dua")
    assert [e.label for e in p.history.list(it.id)] == ["dua", "satu"]


# ---------- thumbnail ----------
def test_thumb_cache_key_changes_with_content(tmp_path):
    p = Project(tmp_path); it = p.add(name="A")
    t1 = thumb_path(p, it); it.code += "// ubah"; assert thumb_path(p, it) != t1
    t2 = thumb_path(p, it); it.width = 640; assert thumb_path(p, it) != t2


def test_make_thumbs_skips_fresh_cleans_stale_and_continues_on_error(tmp_path):
    p = Project(tmp_path); a = p.add(name="A"); b = p.add(name="B")
    calls = []

    def still(project, item, out):
        calls.append(item.id)
        if item.id == b.id:
            raise RuntimeError("Chrome belum ada")
        out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(b"png"); return out

    progress = []
    made, errors = make_thumbs(p, still, lambda n, t, name: progress.append((n, t, name)))
    assert made == 1 and len(errors) == 1 and "B: Chrome" in errors[0] and progress[-1][:2] == (2, 2)
    assert existing_thumb(p, a) and not existing_thumb(p, b)
    calls.clear(); make_thumbs(p, still); assert calls == [b.id]  # a sudah segar
    a.code += "\n// baru"; make_thumbs(p, still)
    assert len(list((tmp_path / ".vm_thumbs").glob(f"{a.id}-*.png"))) == 1  # versi usang dibuang


# ---------- highlight ----------
def kinds(code):
    return [(k, code[s:e]) for k, s, e in tokenize(code)]


def test_highlight_basic_tokens():
    got = kinds('const x = 42; // catatan\nreturn <Sequence from={3}>"hi"</Sequence>;')
    assert ("keyword", "const") in got and ("number", "42") in got and ("comment", "// catatan") in got
    assert ("keyword", "return") in got and ("tag", "<Sequence") in got and ("tag", "</Sequence") in got
    assert ("string", '"hi"') in got and ("number", "3") in got


def test_highlight_string_hides_comment_markers_and_keywords():
    got = kinds('const u = "https://x.com/a"; const t = `a ${b} // c`; /* blok\nbaris */ interpolate(1)')
    strings = [t for k, t in got if k == "string"]
    assert '"https://x.com/a"' in strings and "`a ${b} // c`" in strings
    assert not any(k == "comment" and "x.com" in t for k, t in got)
    assert ("comment", "/* blok\nbaris */") in got and ("func", "interpolate") in got
    assert tokenize("x" * 300_000) == []  # file raksasa dilewati
    assert all(0 <= s < e for _k, s, e in tokenize("a < b && c > d"))


# ---------- cari / ganti ----------
def test_find_and_replace():
    text = "Foo foo FOO bar"
    assert find_all(text, "foo") == [(0, 3), (4, 7), (8, 11)]
    assert find_all(text, "foo", case=True) == [(4, 7)]
    assert find_all(text, r"b\w+", regex=True) == [(12, 15)] and find_all(text, "") == []
    assert find_all("a.b", ".") == [(1, 2)] and find_all("a.b", ".", regex=True) == [(0, 1), (1, 2), (2, 3)]
    assert replace_all(text, "foo", "X") == ("X X X bar", 3)
    assert replace_all("a.b", ".", "-") == ("a-b", 1)  # literal, bukan regex
    assert replace_all("ab12", r"(\d)(\d)", r"\2\1", regex=True) == ("ab21", 1)
    assert replace_all("a\\b", "\\", "/") == ("a/b", 1)
    with pytest.raises(ValueError):
        find_all("x", "(", regex=True)
    with pytest.raises(ValueError):
        replace_all("ab", "a", r"\9", regex=True)


def test_next_match_wraps():
    spans = [(0, 2), (5, 7), (9, 11)]
    assert next_match(spans, 0) == 0 and next_match(spans, 3) == 1 and next_match(spans, 10) == 0  # lingkar
    assert next_match(spans, 5, forward=False) == 0 and next_match(spans, 0, forward=False) == 2
    assert next_match([], 3) is None


# ---------- preset & draft render ----------
def test_presets_apply(tmp_path):
    p = Project(tmp_path); it = p.add(name="A")
    apply_preset(it, "TikTok / Reels / Shorts (9:16)")
    assert (it.width, it.height, it.fps) == (1080, 1920, 30)
    assert all(w > 0 and h > 0 and f > 0 for w, h, f in RENDER_PRESETS.values())
    with pytest.raises(KeyError):
        apply_preset(it, "tidak ada")


def test_draft_scale_in_render_command(tmp_path):
    it = Project(tmp_path).add(name="A")
    full = build_command("npx", it, Path("o.mp4"), RenderOptions())
    assert not any(a.startswith("--scale") for a in full)
    draft = build_command("npx", it, Path("o.mp4"), RenderOptions(scale=0.5))
    assert "--scale=0.5" in draft
    assert not any(a.startswith("--scale") for a in build_command("npx", it, Path("o.gif"), RenderOptions(fmt="gif", scale=0.5)))


# ---------- ekspor / impor ----------
def test_export_import_roundtrip(tmp_path):
    src = Project(tmp_path / "a"); src.add("export const Remotion = () => null; // satu", "Satu", fps=60)
    src.add(name="Dua", width=1080, height=1920); src.write_scaffold()
    (src.assets_dir / "x.png").write_bytes(b"PNG")
    z = tmp_path / "p.zip"
    assert export_project(src, z) == 2
    dst = Project(tmp_path / "b"); dst.add(name="Sudah ada")
    new = import_project(dst, z)
    assert [i.name for i in new] == ["Satu", "Dua"] and [i.id for i in dst.items] == ["scene_001", "scene_002", "scene_003"]
    assert new[0].code.endswith("// satu") and new[0].fps == 60 and (new[1].width, new[1].height) == (1080, 1920)
    assert (dst.assets_dir / "x.png").read_bytes() == b"PNG"


def test_import_rejects_bad_zip_and_zip_slip(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z: z.writestr("readme.txt", "x")
    with pytest.raises(ValueError, match="manifest"):
        import_project(Project(tmp_path / "p"), bad)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "vibemotion-project/1", "items": []}))
        z.writestr("assets/../../pwned.txt", "x"); z.writestr("assets/ok.txt", "ok"); z.writestr("assets/sub/dalam.txt", "x")
    proj = Project(tmp_path / "q"); import_project(proj, evil)
    assert (proj.assets_dir / "ok.txt").exists() and not (tmp_path / "pwned.txt").exists() and not (tmp_path.parent / "pwned.txt").exists()
    assert not (proj.assets_dir / "dalam.txt").exists() and not (proj.assets_dir / "sub").exists()
    wrong = tmp_path / "w.zip"
    with zipfile.ZipFile(wrong, "w") as z: z.writestr("manifest.json", json.dumps({"format": "lain"}))
    with pytest.raises(ValueError, match="Format"):
        import_project(Project(tmp_path / "r"), wrong)


def test_history_order_is_stable_within_the_same_millisecond(tmp_path, monkeypatch):
    """Regresi: snapshot beruntun pada milidetik yang sama dulu bisa tertukar (urutan jatuh ke abjad label)."""
    monkeypatch.setattr("vibemotion.core.history.time.time", lambda: 1_700_000_000.123)
    h = History(tmp_path)
    for label, code in (("zzz", "a"), ("aaa", "b"), ("mmm", "c")):  # label sengaja berlawanan abjad dengan urutan waktu
        assert h.snapshot("v", code, label)
    entries = h.list("v")
    assert [e.label for e in entries] == ["mmm", "aaa", "zzz"] and len({e.id for e in entries}) == 3
    assert [h.read("v", e.id) for e in entries] == ["c", "b", "a"]
    # waktu sistem mundur (mis. koreksi jam): tetap urut
    monkeypatch.setattr("vibemotion.core.history.time.time", lambda: 1_600_000_000.0)
    h.snapshot("v", "d", "baru"); assert h.list("v")[0].label == "baru"
