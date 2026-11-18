import re

import pytest

from vibemotion.core.project import Project
from vibemotion.core.validate import has_remotion_export


@pytest.mark.parametrize("code,ok", [
    ("export const Remotion = () => null;", True),
    ("export const Remotion: React.FC = () => null;", True),
    ("export function Remotion() { return null }", True),
    ("const A = () => null;\nexport { A as Remotion };", True),
    ("export const Judul = () => null;", False),
    ("export default function Intro() { return null }", False),  # default ditangani clean_code_output → alias; di sini mentah
    ("", False),
    ("// export const Remotion\nconst x = 1;", False),
])
def test_has_remotion_export(code, ok):
    assert has_remotion_export(code) is ok


def test_root_never_references_missing_exports_statically(tmp_path):
    """Regresi dari Studio nyata: satu video tanpa ekspor `Remotion` dulu menjatuhkan SELURUH preview
    ('A value of undefined was passed to the component prop')."""
    p = Project(tmp_path)
    for n in range(3): p.add(name=f"V{n}")
    root = p.root_tsx()
    assert 'Remotion as C_' not in root  # impor bernama langsung (undefined bila ekspor tidak ada) tidak dipakai lagi
    assert len(re.findall(r"const C_scene_00\d = pick\(", root)) == 3
    assert 'm["Remotion"] ?? m["default"]' in root and 'typeof c === "function"' in root
    assert "tidak mengekspor komponen" in root  # pesan di dalam video yang bermasalah
    # setiap Composition selalu menerima komponen (hasil pick), tidak pernah impor mentah
    assert len(re.findall(r'<Composition id="scene-00\d" component=\{C_scene_00\d as', root)) == 3


def test_root_audio_wrapper_still_uses_picked_component(tmp_path):
    p = Project(tmp_path); a = p.add(name="A"); p.set_audio(a.id, music="assets/m.mp3")
    root = p.root_tsx()
    assert "<C_scene_001 />" in root and 'const C_scene_001 = pick(' in root
    assert root.index("const C_scene_001 = pick(") < root.index("const W_scene_001")  # pick dulu, baru dibungkus


def test_pick_helper_is_valid_syntax_when_node_available(tmp_path):
    """Bila Node + esbuild ada (mis. di mesin pengembang), seluruh Root.tsx harus bisa dikompilasi."""
    from vibemotion.core.validate import syntax_check
    import shutil
    root_dir = tmp_path
    if not shutil.which("node"):
        pytest.skip("node tidak ada")
    # esbuild hanya ada bila environment Remotion terpasang; cari di lokasi proyek uji manual
    from pathlib import Path
    cand = [Path(p) for p in __import__("os").environ.get("VMN_TEST_PROJECT", "").split(os.pathsep) if p] if (os := __import__("os")) else []
    cand = [c for c in cand if (c / "node_modules" / "esbuild").exists()]
    if not cand:
        pytest.skip("esbuild tidak tersedia (butuh proyek dengan node_modules)")
    p = Project(root_dir); p.add(name="A")
    assert syntax_check(cand[0], p.root_tsx()) is None


def test_comments_do_not_affect_static_checks():
    from vibemotion.core.validate import static_checks
    commented = "// jangan pakai Math.random() atau setTimeout(\n/* export const Remotion = () => null; */\nexport const Remotion = () => 1;"
    assert static_checks(commented) == []  # komentar tidak memicu determinisme; ekspor asli tetap terdeteksi
    only_comment = "/* export const Remotion = () => null; */\nconst x = 1;"
    assert [i.kind for i in static_checks(only_comment)] == ["export"]
    # tanda // di dalam string tidak membuang sisa baris
    with_url = 'const u = "https://x.com/a"; export const Remotion = () => null;'
    assert static_checks(with_url) == [] and has_remotion_export(with_url)
    # kode sungguhan tetap terdeteksi
    assert [i.kind for i in static_checks("export const Remotion = () => Math.random();")] == ["determinism"]
