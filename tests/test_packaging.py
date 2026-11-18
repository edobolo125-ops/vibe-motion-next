import importlib.util
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("ver,exp", [("0.9-alur-editor", (0, 9, 0)), ("1.2.3", (1, 2, 3)), ("2", (2, 0, 0)), ("1.2.3.4", (1, 2, 3))])
def test_numeric_version(ver, exp):
    assert load_tool("make_version_info").numeric(ver) == exp


def test_version_info_text_is_valid_and_has_version():
    text = load_tool("make_version_info").render("0.10-distribusi")
    assert "filevers=(0, 10, 0, 0)" in text and "'ProductVersion', '0.10-distribusi'" in text
    ns = {}
    # berkas ini adalah ekspresi Python (format PyInstaller); stub kelas agar bisa dievaluasi untuk memastikan sintaksnya benar
    stubs = {n: (lambda *a, _n=n, **k: (_n, a, k)) for n in ("VSVersionInfo", "FixedFileInfo", "StringFileInfo", "StringTable", "StringStruct", "VarFileInfo", "VarStruct")}
    result = eval(text, stubs, ns)
    assert result[0] == "VSVersionInfo"


def test_icon_generated_with_all_sizes(tmp_path):
    ico = load_tool("make_icon").main(tmp_path)
    im = Image.open(ico)
    assert {16, 32, 48, 256} <= {s[0] for s in im.ico.sizes()} and (tmp_path / "icon.png").exists()
    assert Image.open(tmp_path / "icon.png").size == (512, 512)


def test_repo_ships_icon_and_spec_references_existing_files():
    spec = (ROOT / "VibeMotionNext.spec").read_text(encoding="utf-8")
    for rel in re.findall(r'"(assets/[\w.]+)"', spec):
        assert (ROOT / rel).exists(), rel
    assert "console=False" in spec and "collect_all(\"customtkinter\")" in spec


def test_installer_and_workflow_consistent():
    iss = (ROOT / "installer" / "VibeMotionNext.iss").read_text(encoding="utf-8")
    assert "{#AppVersion}" in iss and "PrivilegesRequired=lowest" in iss and r"..\dist\VibeMotionNext" in iss
    wf = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "tools/build.py" in wf and "windows-latest" in wf and "actions/checkout@v4" in wf
    assert "VibeMotionNext-Setup-" in wf and "VibeMotionNext-Setup-{#AppVersion}" in iss.replace("OutputBaseFilename=", "")


def test_gitignore_does_not_hide_spec():
    assert "*.spec" not in (ROOT / ".gitignore").read_text()


def test_resource_path_dev_and_frozen(monkeypatch, tmp_path):
    from vibemotion.resources import resource_path
    assert (resource_path("assets/icon.ico")).exists()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("assets/icon.ico") == tmp_path / "assets" / "icon.ico"


def test_find_iscc_uses_path_then_standard_dirs(monkeypatch, tmp_path):
    build = load_tool("build")
    monkeypatch.setattr(build.shutil, "which", lambda n: "C:/x/iscc.exe" if n == "iscc" else None)
    assert build.find_iscc() == "C:/x/iscc.exe"
    monkeypatch.setattr(build.shutil, "which", lambda n: None)
    assert build.find_iscc() is None or Path(build.find_iscc()).exists()  # tidak ada Inno di mesin uji → None
    inno = tmp_path / "Inno Setup 6"; inno.mkdir(); (inno / "ISCC.exe").write_bytes(b"MZ")
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path)); monkeypatch.delenv("ProgramFiles", raising=False)
    assert build.find_iscc() == str(inno / "ISCC.exe")


def test_workflow_tests_installer_on_real_windows_and_yaml_is_valid():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8"))
    names = [s.get("name", "") for s in wf["jobs"]["windows"]["steps"]]
    assert any("Uji pada Windows" in n for n in names)
    text = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "check_windows.py --exe" in text and "--installer $setup.FullName" in text


def test_release_notes_exist_and_tag_versions_compare_correctly():
    from vibemotion.core.updater import is_newer
    assert (ROOT / "RELEASING.md").exists()
    assert not is_newer("v0.14.0", "0.14-distribusi") and is_newer("v0.14.1", "0.14-distribusi") and is_newer("v0.15.0", "0.14-distribusi")
