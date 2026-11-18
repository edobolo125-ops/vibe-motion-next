import json

import pytest

from vibemotion.ai.base import AIError
from vibemotion.ai.extras import PLAN_SYSTEM, REVIEW_SYSTEM, adapt_ratio, edit_checked
from vibemotion.ai.pipeline import generate_videos, make_ratio_variants, make_variations
from vibemotion.ai.prompts import GenerationSpec
from vibemotion.ai.service import AIService
from vibemotion.core.library import SavedPrompts, UserTemplates
from vibemotion.core.portable import export_project, import_project
from vibemotion.core.project import Project
from vibemotion.core.validate import Issue
from vibemotion.templates import TEMPLATES

GOOD = "export const Remotion = () => null;"


# ---------- varian rasio ----------
def test_ratio_variants_copy_and_skip_same_size(tmp_path):
    p = Project(tmp_path); a = p.add(GOOD, "Intro", width=1920, height=1080, fps=24, duration_sec=5)
    b = p.add(name="Lain")
    new = p.variants(a.id, {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)})
    assert [i.name for i in new] == ["Intro (9:16)", "Intro (1:1)"]  # 16:9 sama dengan sumber → dilewati
    assert [(i.width, i.height, i.fps, i.duration_sec, i.code) for i in new] == [(1080, 1920, 24, 5, GOOD), (1080, 1080, 24, 5, GOOD)]
    assert [i.name for i in p.items] == ["Intro", "Intro (9:16)", "Intro (1:1)", "Lain"]  # disisipkan tepat setelah sumber
    assert len({i.id for i in p.items}) == 4


# ---------- audio ----------
def test_set_audio_clamps_and_clears(tmp_path):
    p = Project(tmp_path); a = p.add(name="A")
    p.set_audio(a.id, music="assets/m.mp3", volume=7, voiceover="assets/v.wav")
    assert (a.music, a.music_volume, a.voiceover, a.has_audio) == ("assets/m.mp3", 1.0, "assets/v.wav", True)
    p.set_audio(a.id, volume=-3); assert a.music_volume == 0.0
    p.set_audio(a.id, music="", voiceover=""); assert not a.has_audio


def test_root_without_audio_is_unchanged_and_with_audio_wraps(tmp_path):
    p = Project(tmp_path); a = p.add(name="A", fps=30, duration_sec=10); b = p.add(name="B")
    plain = p.root_tsx()
    assert "W_" not in plain and 'import { AbsoluteFill, Composition } from "remotion"' in plain and "<Audio" not in plain
    p.set_audio(a.id, music='assets/lagu "x".mp3', volume=0.4, voiceover="assets/vo.wav")
    root = p.root_tsx()
    assert "const W_scene_001" in root and "W_scene_002" not in root
    assert 'component={W_scene_001 as' in root and 'component={C_scene_002 as' in root
    assert r'staticFile("assets/lagu \"x\".mp3")' in root  # tanda kutip di-escape (json.dumps)
    assert "loop" in root and "[0, 30, 255, 300], [0, 0.4, 0.4, 0]" in root  # fade 1 dtk masuk, 1.5 dtk keluar
    assert 'staticFile("assets/vo.wav")' in root and "import { AbsoluteFill, Audio, Composition, interpolate, staticFile }" in root


def test_audio_fade_ranges_stay_ascending_for_tiny_videos(tmp_path):
    p = Project(tmp_path)
    for secs in (0.1, 0.5, 1, 2):
        a = p.add(name=f"v{secs}", fps=30, duration_sec=secs); p.set_audio(a.id, music="assets/m.mp3")
    import re
    for rng in re.findall(r"interpolate\(f, \[([^\]]+)\]", p.root_tsx()):
        nums = [int(x) for x in rng.split(",")]
        assert nums == sorted(nums) and len(set(nums)) == 4, nums  # interpolate Remotion butuh rentang naik ketat


def test_audio_persists_and_exports(tmp_path):
    p = Project(tmp_path / "a"); a = p.add(name="A"); p.set_audio(a.id, music="assets/m.mp3", volume=0.3, voiceover="assets/v.wav"); p.save()
    q = Project(tmp_path / "a"); q.load(); i = q.items[0]
    assert (i.music, i.music_volume, i.voiceover) == ("assets/m.mp3", 0.3, "assets/v.wav")
    z = tmp_path / "p.zip"; export_project(p, z)
    r = Project(tmp_path / "b"); new = import_project(r, z)
    assert (new[0].music, new[0].music_volume, new[0].voiceover) == ("assets/m.mp3", 0.3, "assets/v.wav")
    assert Project(tmp_path / "c").add(name="x").music == ""  # lama/tanpa audio: bawaan kosong


def test_old_state_without_audio_fields_loads(tmp_path):
    p = Project(tmp_path); p.add(name="Lama"); p.save()
    meta = json.loads((tmp_path / "vibemotion.json").read_text())
    for m in meta: [m.pop(k, None) for k in ("music", "music_volume", "voiceover")]
    (tmp_path / "vibemotion.json").write_text(json.dumps(meta))
    q = Project(tmp_path); q.load(); assert q.items[0].music == "" and q.items[0].music_volume == 0.5


# ---------- pustaka pribadi ----------
def test_saved_prompts(tmp_path):
    sp = SavedPrompts(tmp_path / "prompts.json")
    assert sp.names() == []
    sp.save(" Intro keren ", "  Buat intro neon  "); sp.save("alpha", "x")
    assert sp.names() == ["alpha", "Intro keren"] and sp.get("Intro keren") == "Buat intro neon"
    sp.save("alpha", "diganti"); assert sp.get("alpha") == "diganti" and len(sp.names()) == 2
    assert sp.delete("alpha") and not sp.delete("alpha") and sp.names() == ["Intro keren"]
    for bad in (("", "x"), ("n", "  ")):
        with pytest.raises(ValueError): sp.save(*bad)
    (tmp_path / "prompts.json").write_text("{rusak"); assert sp.names() == []  # file rusak → kosong, tidak crash


def test_user_templates(tmp_path):
    ut = UserTemplates(tmp_path / "t")
    assert ut.list() == []
    t = ut.save("Intro saya!", GOOD, 7); assert t.key == "Intro_saya" and t.seconds == 7
    ut.save("Anu", "export const Remotion = () => 1;", 3)
    assert [x.name for x in ut.list()] == ["Anu", "Intro saya!"] and ut.list()[1].code == GOOD
    (tmp_path / "t" / "rusak.json").write_text("{x"); (tmp_path / "t" / "yatim.json").write_text('{"name": "Yatim"}')
    assert [x.name for x in ut.list()] == ["Anu", "Intro saya!"]  # entri rusak / tanpa .tsx dilewati
    assert ut.delete("Anu") and not ut.delete("Anu") and ut.delete("../../etc/passwd") is False
    with pytest.raises(ValueError): ut.save("", GOOD)
    with pytest.raises(ValueError): ut.save("x", "  ")


@pytest.mark.parametrize("key", ["quote", "stat", "logo", "bars"])
def test_new_templates_valid(key):
    from vibemotion.core.validate import static_checks
    t = TEMPLATES[key]; assert static_checks(t.code) == [] and "useVideoConfig" in t.code and t.seconds > 0


# ---------- edit divalidasi, adaptasi, variasi ----------
class Script:
    def __init__(self, edit_replies, fix_replies=(GOOD,), fail_edit_on=None):
        self.edits, self.fixes, self.calls, self.fail_edit_on = list(edit_replies), list(fix_replies), [], fail_edit_on
    def complete(self, system, user, images=None):
        self.calls.append((system[:25], user))
        if system.startswith("Kamu mengedit"):
            if self.fail_edit_on is not None and len([c for c in self.calls if c[0].startswith("Kamu mengedit")]) == self.fail_edit_on:
                raise AIError("503")
            return self.edits.pop(0) if len(self.edits) > 1 else self.edits[0]
        return self.fixes.pop(0) if len(self.fixes) > 1 else self.fixes[0]


bad_validator = lambda c: [Issue("syntax", "BAD")] if "BAD" in c else []


def svc(*a, **k): return AIService(Script(*a, **k), skills_loader=lambda: "")


def test_edit_checked_fixes_bad_edit():
    s = svc(["export const Remotion = () => BAD;"], [GOOD])
    code, issues = edit_checked(s, GOOD, "lebih cepat", None, bad_validator)
    assert "BAD" not in code and issues == []
    stuck, left = edit_checked(svc(["export const Remotion = () => BAD;"], ["export const Remotion = () => BAD;"]), GOOD, "x", None, bad_validator, max_fixes=1)
    assert left


def test_adapt_ratio_prompt_mentions_sizes():
    s = svc([GOOD]); adapt_ratio(s, GOOD, (1920, 1080), (1080, 1920), None, lambda c: [])
    assert "dari 1920x1080 ke 1080x1920" in s.provider.calls[0][1] and "useVideoConfig()" in s.provider.calls[0][1]


def test_make_variations_adds_named_items_with_history_and_cleans_up_on_error(tmp_path):
    p = Project(tmp_path); a = p.add(GOOD, "Asli", fps=24, duration_sec=4); p.set_audio(a.id, music="assets/m.mp3")
    s = svc(["export const Remotion = () => 'v';"])
    made, notes = make_variations(s, p, a.id, 2, auto_check=False)
    assert [m.name for m in made] == ["Asli · var 1", "Asli · var 2"] and notes == [] and all(m.music == "assets/m.mp3" for m in made)
    assert (made[0].fps, made[0].duration_sec) == (24, 4) and any(e.label == "AI variasi" for e in p.history.list(made[0].id))
    users = [c[1] for c in s.provider.calls if c[0].startswith("Kamu mengedit")]
    assert any("VARIASI ke-1" in u for u in users) and any("VARIASI ke-2" in u for u in users)
    before = len(p.items)
    with pytest.raises(AIError):
        make_variations(svc([GOOD], fail_edit_on=2), p, a.id, 3, auto_check=False)
    assert len(p.items) == before + 1  # variasi 1 sukses (dipertahankan), variasi 2 gagal (dibuang)


def test_make_ratio_variants_copy_only_and_with_ai(tmp_path):
    p = Project(tmp_path); a = p.add(GOOD, "V", width=1920, height=1080)
    items, notes = make_ratio_variants(None, p, a.id, {"9:16": (1080, 1920)}, auto_check=False)
    assert [i.name for i in items] == ["V (9:16)"] and items[0].code == GOOD and notes == []
    s = svc(["export const Remotion = () => 'adaptif';"])
    items, notes = make_ratio_variants(s, p, a.id, {"1:1": (1080, 1080), "4:5": (1080, 1350)}, adapt_with_ai=True, auto_check=False)
    assert all("adaptif" in i.code for i in items) and notes == []
    assert any("dari 1920x1080 ke 1080x1080" in c[1] for c in s.provider.calls)
    assert any("dari 1920x1080 ke 1080x1350" in c[1] for c in s.provider.calls)
    # AI gagal pada satu rasio: tetap salinan asli + catatan, rasio lain jalan
    p2 = Project(tmp_path / "2"); b = p2.add(GOOD, "W", width=1920, height=1080)
    items, notes = make_ratio_variants(svc([GOOD], fail_edit_on=1), p2, b.id, {"1:1": (1080, 1080), "4:5": (1080, 1350)}, adapt_with_ai=True, auto_check=False)
    assert len(items) == 2 and len(notes) == 1 and "adaptasi AI gagal" in notes[0] and items[0].code == GOOD


def test_compare_label_in_names(tmp_path):
    p = Project(tmp_path)
    s = svc([GOOD], [GOOD])
    class P:
        def complete(self, system, user, images=None): return GOOD
    items, _ = generate_videos(AIService(P(), skills_loader=lambda: ""), p, GenerationSpec(), "x", auto_check=False, label="gemini-x")
    assert items[0].name == "Video 1 · gemini-x"
