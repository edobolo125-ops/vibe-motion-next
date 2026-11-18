import json
from pathlib import Path

import pytest

from vibemotion.config import Settings
from vibemotion.core.code_utils import (clean_code_output, parse_duration_to_seconds, safe_filename)
from vibemotion.core.preview import ErrorCollector
from vibemotion.core.project import Project
from vibemotion.core.render import RenderOptions, build_command, parse_progress
from vibemotion.core.versions import REMOTION_VERSION, package_json_dependencies


def test_clean_strips_fences_and_prose():
    raw = "Tentu, ini kodenya:\n```tsx\nexport const Remotion = () => <div/>;\n```\nSemoga membantu"
    out = clean_code_output(raw)
    assert out.startswith('import React from "react";')
    assert "Tentu" not in out and "```" not in out and "export const Remotion" in out


def test_clean_default_export_gets_named_alias():
    out = clean_code_output('import React from "react";\nexport default function Intro(){return null}')
    assert "export { Intro as Remotion };" in out


def test_clean_keeps_urls_with_double_slash():
    out = clean_code_output('export const Remotion = () => <img src="https://x.com/a.png" />;')
    assert "https://x.com/a.png" in out


@pytest.mark.parametrize("text,exp", [("30", 30), ("30s", 30), ("1.5 menit", 90), ("2m", 120),
                                       ("1m30s", 90), ("", 10), ("abc", 10)])
def test_duration(text, exp):
    assert parse_duration_to_seconds(text) == exp


def test_safe_filename():
    assert safe_filename('a/b:c*?') == "a_b_c__"
    assert safe_filename("  ..  ") == "video"


def test_versions_are_pinned_and_consistent():
    deps = package_json_dependencies()
    assert deps["zod"] == "4.6.7"
    for k, v in deps.items():
        assert not v.startswith(("^", "~")), k
        if k == "remotion" or k.startswith("@remotion/"):
            assert v == REMOTION_VERSION


def test_project_roundtrip_and_root(tmp_path):
    p = Project(tmp_path)
    a = p.add(name="A")
    b = p.add("export const Remotion = () => null;", name="B", fps=60, duration_sec=2)
    p.save()
    root = (tmp_path / "src" / "Root.tsx").read_text()
    # akar masalah warning lama: tidak boleh ada akses statis .default / myCompSchema (webpack "export not found");
    # namespace disalin lewat Object.assign dan komponen dipilih aman oleh pick()
    assert ".default" not in root and "myCompSchema" not in root and "UserModule" not in root
    assert 'import * as M_scene_001 from "./compositions/scene_001"' in root and "Object.assign({}, mod)" in root
    assert 'const C_scene_001 = pick("scene_001", M_scene_001);' in root
    assert "durationInFrames={120}" in root and 'id="scene-002"' in root
    pkg = json.loads((tmp_path / "package.json").read_text())
    assert pkg["dependencies"]["zod"] == "4.6.7"
    q = Project(tmp_path); q.load()
    assert [i.name for i in q.items] == ["A", "B"] and q.items[1].fps == 60
    assert q.items[1].code.startswith("export const Remotion")


def test_project_ops(tmp_path):
    p = Project(tmp_path)
    a, b = p.add(name="A"), p.add(name="B")
    c = p.duplicate(a.id)
    assert [i.name for i in p.items] == ["A", "A (copy)", "B"] and c.id == "scene_003"
    p.move(b.id, -1)
    assert [i.name for i in p.items] == ["A", "B", "A (copy)"]
    m = p.merge([a.id, b.id])
    assert "Series.Sequence" in m.code and m.duration_sec == 20
    p.remove(a.id)
    p.save()
    assert not (tmp_path / "src" / "compositions" / "scene_001.tsx").exists()
    with pytest.raises(ValueError):
        p.merge([b.id])


def test_assets(tmp_path):
    src = tmp_path / "x.png"; src.write_bytes(b"1")
    p = Project(tmp_path / "proj")
    assert p.import_asset(src) == "assets/x.png"
    assert p.list_assets() == ["assets/x.png"]


def test_render_command_and_progress():
    p = Project(Path("."))
    item = p.add(name="n")
    cmd = build_command("npx", item, Path("o.mp4"), RenderOptions(concurrency=4))
    assert cmd[:4] == ["npx", "remotion", "render", "src/index.ts"] and "scene-001" in cmd
    assert "--concurrency" in cmd and "--hardware-acceleration=if-possible" in cmd
    assert parse_progress("Rendered 30/60, time remaining: 3s") == 0.5
    assert parse_progress("Encoded 60/60") == 1.0
    assert parse_progress("Server ready 12/34") is None
    with pytest.raises(ValueError):
        build_command("npx", item, Path("o"), RenderOptions(fmt="avi"))


def test_error_collector():
    c = ErrorCollector()
    for line in ["Building...", "ERROR in ./src/compositions/scene_001.tsx 12:3",
                 "Unexpected token", "Built in 100ms"]:
        c.feed(line)
    assert "Unexpected token" in c.text and c.text.startswith("ERROR in")
    c.clear(); assert c.text == ""


def test_settings_roundtrip_ignores_unknown(tmp_path):
    f = tmp_path / "c.json"
    s = Settings(gemini_keys=["a", "b"], fps=24); s.save(f)
    raw = json.loads(f.read_text()); raw["bogus"] = 1; f.write_text(json.dumps(raw))
    t = Settings.load(f)
    assert t.gemini_keys == ["a", "b"] and t.fps == 24
    assert Settings.load(tmp_path / "missing.json").fps == 30


def test_ratios_include_portrait_sizes():
    from vibemotion.config import RATIOS
    assert RATIOS["9:16"] == (1080, 1920) and RATIOS["2:3"] == (1080, 1620)
