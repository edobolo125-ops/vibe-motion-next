import json
from pathlib import Path

import pytest

from vibemotion.ai.base import AIError
from vibemotion.ai import extras
from vibemotion.ai.extras import (REVIEW_SYSTEM, PLAN_SYSTEM, extract_json, generate_checked, generate_reviewed,
                                  plan_scenes, review_visual, transcribe)
from vibemotion.ai.gemini import GeminiProvider
from vibemotion.ai.pipeline import generate_videos
from vibemotion.ai.prompts import GenerationSpec
from vibemotion.ai.service import AIService
from vibemotion.core.project import Project
from vibemotion.core.validate import Issue, issues_to_text, static_checks
from vibemotion.templates import TEMPLATES

GOOD = "export const Remotion = () => null;"
BAD = "export const Remotion = () => BAD;"


class Script:
    """Provider palsu: balasan berdasarkan jenis prompt sistem."""
    def __init__(self, gen=GOOD, fixes=(GOOD,), review=None, plan=None):
        self.gen, self.fixes, self.review, self.plan = gen, list(fixes), review, plan
        self.calls = []

    def complete(self, system, user, images=None):
        self.calls.append((system[:20], user[:60], len(images or [])))
        if system == REVIEW_SYSTEM:
            if isinstance(self.review, Exception): raise self.review
            return self.review if self.review is not None else '{"ok": true, "problems": []}'
        if system == PLAN_SYSTEM:
            return self.plan
        if "Perbaiki error" in system or "Perbaiki" in system[:40]:
            return self.fixes.pop(0) if len(self.fixes) > 1 else self.fixes[0]
        return self.gen


def validator(code):
    return [Issue("syntax", "BAD")] if "BAD" in code else []


def test_extract_json_variants():
    assert extract_json('Ini:\n```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert extract_json('teks {"ok": false} lagi') == {"ok": False}
    assert extract_json('{"ok": false, "problems": ["a", "b"]}') == {"ok": False, "problems": ["a", "b"]}
    assert extract_json('[{"k": [1]}]') == [{"k": [1]}]
    with pytest.raises(AIError):
        extract_json("tidak ada json")


def test_generate_checked_fixes_then_stops():
    svc = AIService(Script(gen=BAD, fixes=(GOOD,)), skills_loader=lambda: "")
    status = []
    code, issues = generate_checked(svc, GenerationSpec(), "x", None, validator, on_status=status.append)
    assert "BAD" not in code and issues == [] and len(status) == 1
    # fix terus rusak -> berhenti di max_fixes dan melaporkan sisa masalah
    svc = AIService(Script(gen=BAD, fixes=(BAD,)), skills_loader=lambda: "")
    code, issues = generate_checked(svc, GenerationSpec(), "x", None, validator, max_fixes=2)
    assert issues and sum(1 for c in svc.provider.calls if "Perbaiki" in c[0] or c[0].startswith("Kode Remotion")) == 2


def test_generate_checked_survives_fix_failure():
    class Boom(Script):
        def complete(self, system, user, images=None):
            if "gagal dikompilasi" in system: raise AIError("down")
            return super().complete(system, user, images)
    code, issues = generate_checked(AIService(Boom(gen=BAD), skills_loader=lambda: ""), GenerationSpec(), "x", None, validator)
    assert "BAD" in code and issues  # tidak crash


def test_review_visual_parsing_and_failure_is_lenient(tmp_path):
    png = tmp_path / "s.png"; png.write_bytes(b"x")
    svc = AIService(Script(review='{"ok": false, "problems": ["teks terpotong"]}'), skills_loader=lambda: "")
    assert review_visual(svc, png, "req") == (False, "- teks terpotong")
    assert review_visual(AIService(Script(review="bukan json"), skills_loader=lambda: ""), png, "r") == (True, "")
    assert review_visual(AIService(Script(review=AIError("x")), skills_loader=lambda: ""), png, "r") == (True, "")
    # ok=false tanpa masalah konkret dianggap lolos
    assert review_visual(AIService(Script(review='{"ok": false, "problems": []}'), skills_loader=lambda: ""), png, "r")[0]


def test_generate_reviewed_applies_visual_fix_but_never_with_broken_code(tmp_path):
    png = tmp_path / "s.png"; png.write_bytes(b"x")
    fixed = "export const Remotion = () => 'lebih baik';"
    svc = AIService(Script(gen=GOOD, fixes=(fixed,), review='{"ok": false, "problems": ["kontras buruk"]}'), skills_loader=lambda: "")
    code, issues = generate_reviewed(svc, GenerationSpec(), "x", None, validator, lambda c: png)
    assert "'lebih baik'" in code and issues == []
    svc = AIService(Script(gen=GOOD, fixes=(BAD,), review='{"ok": false, "problems": ["x"]}'), skills_loader=lambda: "")
    code, _ = generate_reviewed(svc, GenerationSpec(), "x", None, validator, lambda c: png)
    assert "BAD" not in code  # perbaikan rusak ditolak
    # render still gagal -> lewati tinjauan, kode tetap dipakai
    svc = AIService(Script(gen=GOOD), skills_loader=lambda: "")
    def broken(_c): raise RuntimeError("Chrome belum ada")
    assert "BAD" not in generate_reviewed(svc, GenerationSpec(), "x", None, validator, broken)[0]


def test_plan_scenes_normalizes():
    plan = json.dumps([{"title": "Hook", "brief": "a", "seconds": 2}, {"title": "Isi", "brief": "b", "seconds": 6},
                       {"title": "Penutup", "brief": "c", "seconds": "x"}, {"title": "Ekstra", "brief": "d"}])
    svc = AIService(Script(plan=plan), skills_loader=lambda: "")
    scenes = plan_scenes(svc, "ide", 3, 30)
    assert [s.title for s in scenes] == ["Hook", "Isi", "Penutup"]  # dipotong sesuai jumlah
    assert abs(sum(s.seconds for s in scenes) - 30) < 0.5 and all(s.seconds >= 1 for s in scenes)
    with pytest.raises(AIError):
        plan_scenes(AIService(Script(plan="[]"), skills_loader=lambda: ""), "ide", 3, 30)
    with pytest.raises(AIError):
        plan_scenes(AIService(Script(plan='["bukan objek"]'), skills_loader=lambda: ""), "ide", 3, 30)


class FakeHTTP:
    def __init__(self, text): self.text = text; self.calls = []
    def post(self, url, **kw):
        self.calls.append(kw)
        class R:  # noqa
            status_code = 200
            def json(s): return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}
        return R()


def test_transcribe(tmp_path, monkeypatch):
    audio = tmp_path / "a.mp3"; audio.write_bytes(b"ID3")
    raw = '```json\n[{"start": 2, "end": 3.5, "text": "dua"}, {"start": 0, "end": 1.2, "text": "satu"}, {"start": 5, "end": 4, "text": "rusak"}, {"x": 1}]\n```'
    http = FakeHTTP(raw)
    svc = AIService(GeminiProvider(["k"], "m", session=http), skills_loader=lambda: "")
    caps = transcribe(svc, audio)
    assert [c["text"] for c in caps] == ["satu", "dua"]
    part = http.calls[0]["json"]["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "audio/mpeg"
    with pytest.raises(AIError, match="Gemini"):
        transcribe(AIService(Script(), skills_loader=lambda: ""), audio)
    monkeypatch.setattr(extras, "MAX_INLINE_MB", 0)
    with pytest.raises(AIError, match="terlalu besar"):
        transcribe(svc, audio)


def test_write_captions(tmp_path):
    p = Project(tmp_path)
    ref = p.write_captions([{"start": 0, "end": 1, "text": "é"}], "my talk")
    assert ref == "assets/my talk.json"
    assert json.loads((tmp_path / "public/assets/my talk.json").read_text(encoding="utf-8"))[0]["text"] == "é"


def test_pipeline_single_variations_and_cleanup(tmp_path):
    p = Project(tmp_path); p.add(name="Awal")
    svc = AIService(Script(gen=GOOD), skills_loader=lambda: "")
    items, notes = generate_videos(svc, p, GenerationSpec(width=1080, height=1920, fps=24, duration_sec=4), "x",
                                   count=2, auto_check=False)
    assert [i.name for i in items] == ["Video 2", "Video 3"] and notes == []
    assert items[0].code.endswith(GOOD + "\n") and (items[0].width, items[0].fps) == (1080, 24)
    assert (tmp_path / "src/compositions" / f"{items[0].id}.tsx").read_text().endswith(GOOD + "\n")
    # gagal di tengah: item gagal dibuang, yang sebelumnya tetap ada
    class Flaky(Script):
        n = 0
        def complete(self, system, user, images=None):
            Flaky.n += 1
            if Flaky.n == 2: raise AIError("503")
            return super().complete(system, user, images)
    before = len(p.items)
    with pytest.raises(AIError):
        generate_videos(AIService(Flaky(), skills_loader=lambda: ""), p, GenerationSpec(), "x", count=3, auto_check=False)
    assert len(p.items) == before + 1


def test_pipeline_storyboard_merge(tmp_path):
    p = Project(tmp_path)
    plan = json.dumps([{"title": "A", "brief": "satu", "seconds": 3}, {"title": "B", "brief": "dua", "seconds": 3}])
    svc = AIService(Script(plan=plan), skills_loader=lambda: "")
    items, notes = generate_videos(svc, p, GenerationSpec(duration_sec=6), "ide", mode="storyboard", scenes=2,
                                   merge=True, auto_check=False)
    assert [i.name for i in items] == ["A", "B", "Storyboard"] and items[2].duration_sec == 6
    assert "Series.Sequence" in items[2].code
    user_msgs = [c[1] for c in svc.provider.calls]
    assert any("adegan 1 dari 2" in m for m in user_msgs) and any("adegan 2 dari 2" in m for m in user_msgs)


def test_pipeline_reports_remaining_issues(tmp_path):
    p = Project(tmp_path)
    svc = AIService(Script(gen=BAD, fixes=(BAD,)), skills_loader=lambda: "")
    import vibemotion.ai.pipeline as pl
    orig = pl.make_validator
    pl.make_validator = lambda project, enabled: validator
    try:
        items, notes = generate_videos(svc, p, GenerationSpec(), "x", auto_check=True)
    finally:
        pl.make_validator = orig
    assert len(items) == 1 and "BAD" in notes[0]


def test_static_checks_cases(tmp_path):
    nm = tmp_path / "node_modules"; (nm / "lucide-react").mkdir(parents=True); (nm / "@remotion/shapes").mkdir(parents=True)
    (tmp_path / "public/assets").mkdir(parents=True); (tmp_path / "public/assets/a.png").write_bytes(b"1")
    ok = ('import React from "react";\nimport {staticFile} from "remotion";\nimport {Heart} from "lucide-react";\n'
          'import {Circle} from "@remotion/shapes";\nconst a = staticFile("assets/a.png");\nexport const Remotion = () => null;')
    assert static_checks(ok, tmp_path) == []
    kinds = lambda c: sorted(i.kind for i in static_checks(c, tmp_path))
    assert kinds('import x from "three";\nexport const Remotion=()=>null;') == ["package"]
    assert kinds('import x from "@remotion/lottie";\nexport const Remotion=()=>null;') == ["package"]
    assert kinds("const x = 1;") == ["export"]
    assert kinds('export const Remotion=()=>Math.random();') == ["determinism"]
    assert "[export]" in issues_to_text(static_checks("x", tmp_path))
    # tanpa node_modules: paket tidak diperiksa
    assert static_checks('import x from "three";\nexport const Remotion=()=>null;', tmp_path / "kosong") == []


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_templates_are_valid(key):
    t = TEMPLATES[key]
    assert static_checks(t.code) == [] and "useVideoConfig" in t.code and t.seconds > 0
