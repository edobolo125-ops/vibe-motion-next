"""Model proyek: daftar video + penulisan file proyek Remotion.

Setiap video = satu file `src/compositions/<id>.tsx` yang mengekspor `Remotion`.
`src/Root.tsx` dibuat ulang dari daftar video dan mengimpor ekspor bernama itu,
sehingga tidak ada lagi peringatan webpack "export 'default' was not found".
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .code_utils import seconds_to_frames
from .fsutil import atomic_write
from .history import History
from .versions import REMOTION_VERSION, package_json_dependencies

PLACEHOLDER_CODE = '''import React from "react";
import { AbsoluteFill } from "remotion";

export const Remotion: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0d14", justifyContent: "center", alignItems: "center" }} />
  );
};
'''


@dataclass
class VideoItem:
    id: str
    name: str
    code: str = PLACEHOLDER_CODE
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration_sec: float = 10.0
    music: str = ""            # path aset (assets/xxx.mp3) untuk musik latar; kosong = tanpa musik
    music_volume: float = 0.5  # 0..1
    voiceover: str = ""        # path aset untuk voice-over (volume penuh)

    @property
    def has_audio(self) -> bool:
        return bool(self.music or self.voiceover)

    @property
    def frames(self) -> int:
        return seconds_to_frames(self.duration_sec, self.fps)

    @property
    def comp_id(self) -> str:
        return self.id.replace("_", "-")


_ID_RE = re.compile(r"^scene_(\d+)$")


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.items: list[VideoItem] = []
        self.history = History(self.root)

    def snapshot(self, video_id: str, label: str = "manual"):
        """Simpan versi kode video ini ke riwayat (None bila tak berubah)."""
        return self.history.snapshot(video_id, self.get(video_id).code, label)

    # ---------- paths ----------
    @property
    def src(self) -> Path:
        return self.root / "src"

    @property
    def comp_dir(self) -> Path:
        return self.src / "compositions"

    @property
    def assets_dir(self) -> Path:
        return self.root / "public" / "assets"

    @property
    def state_file(self) -> Path:
        return self.root / "vibemotion.json"

    # ---------- items ----------
    def next_id(self) -> str:
        used = [int(m.group(1)) for i in self.items if (m := _ID_RE.match(i.id))]
        return f"scene_{(max(used) + 1) if used else 1:03d}"

    def add(self, code: str = PLACEHOLDER_CODE, name: str | None = None, **opts) -> VideoItem:
        vid = self.next_id()
        item = VideoItem(id=vid, name=name or f"Video {len(self.items) + 1}", code=code, **opts)
        self.items.append(item)
        return item

    def get(self, video_id: str) -> VideoItem:
        for item in self.items:
            if item.id == video_id:
                return item
        raise KeyError(video_id)

    def remove(self, video_id: str) -> None:
        self.items = [i for i in self.items if i.id != video_id]

    def duplicate(self, video_id: str) -> VideoItem:
        src = self.get(video_id)
        copy = VideoItem(**{**asdict(src), "id": self.next_id(), "name": f"{src.name} (copy)"})
        self.items.insert(self.items.index(src) + 1, copy)
        return copy

    def variants(self, video_id: str, ratios: dict[str, tuple[int, int]]) -> list[VideoItem]:
        """Salin video ke beberapa ukuran/rasio. Nama: '<asli> (9:16)'. Kode sama (layout responsif via useVideoConfig)."""
        src = self.get(video_id)
        out: list[VideoItem] = []
        at = self.items.index(src) + 1
        for label, (w, h) in ratios.items():
            if (w, h) == (src.width, src.height):
                continue  # ukuran yang sama dengan sumber: tidak perlu varian
            copy = VideoItem(**{**asdict(src), "id": self.next_id(), "name": f"{src.name} ({label})",
                                "width": w, "height": h})
            self.items.insert(at, copy)
            at += 1
            out.append(copy)
        return out

    def set_audio(self, video_id: str, music: str | None = None, volume: float | None = None,
                  voiceover: str | None = None) -> VideoItem:
        """None = biarkan; "" = hapus. Volume dijepit ke 0..1."""
        it = self.get(video_id)
        if music is not None:
            it.music = music
        if voiceover is not None:
            it.voiceover = voiceover
        if volume is not None:
            it.music_volume = min(1.0, max(0.0, float(volume)))
        return it

    def move(self, video_id: str, delta: int) -> None:
        idx = next(i for i, it in enumerate(self.items) if it.id == video_id)
        new = idx + delta
        if 0 <= new < len(self.items):
            self.items[idx], self.items[new] = self.items[new], self.items[idx]

    def merge(self, ids: list[str], name: str = "Merged") -> VideoItem:
        """Gabung beberapa video berurutan memakai <Series>."""
        parts = [self.get(i) for i in ids]
        if len(parts) < 2:
            raise ValueError("need at least 2 videos")
        imports, seq = [], []
        for n, p in enumerate(parts, 1):
            imports.append(f'import {{ Remotion as Part{n} }} from "./{p.id}";')
            seq.append(f"      <Series.Sequence durationInFrames={{{p.frames}}}><Part{n} /></Series.Sequence>")
        code = (
            'import React from "react";\nimport { Series } from "remotion";\n'
            + "\n".join(imports)
            + "\n\nexport const Remotion: React.FC = () => (\n    <Series>\n"
            + "\n".join(seq)
            + "\n    </Series>\n);\n"
        )
        first = parts[0]
        return self.add(code, name, width=first.width, height=first.height, fps=first.fps,
                        duration_sec=sum(p.duration_sec for p in parts))

    # ---------- persistence ----------
    def save(self) -> None:
        self.write_files()
        meta = [{k: v for k, v in asdict(i).items() if k != "code"} for i in self.items]
        atomic_write(self.state_file, json.dumps(meta, indent=2, ensure_ascii=False))

    def load(self) -> None:
        self.items = []
        meta: list = []
        try:
            meta = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(meta, list):
                raise ValueError("bad state")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # state rusak: simpan salinannya, lalu pulihkan dari file .tsx yang ada
            try:
                self.state_file.replace(self.state_file.with_suffix(".corrupt.json"))
            except OSError:
                pass
            meta = [{"id": f.stem, "name": f.stem} for f in sorted(self.comp_dir.glob("scene_*.tsx"))]
        allowed = {"id", "name", "width", "height", "fps", "duration_sec", "music", "music_volume", "voiceover"}
        for m in meta:
            try:
                f = self.comp_dir / f"{m['id']}.tsx"
                code = f.read_text(encoding="utf-8") if f.exists() else PLACEHOLDER_CODE
                self.items.append(VideoItem(code=code, **{k: v for k, v in m.items() if k in allowed}))
            except (KeyError, TypeError, OSError):
                continue
        if not self.items:
            self.add()

    # ---------- file generation ----------
    def write_scaffold(self) -> None:
        """File tetap proyek (idempotent)."""
        self.src.mkdir(parents=True, exist_ok=True)
        self.comp_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        (self.root / "package.json").write_text(self.package_json(), encoding="utf-8")
        (self.root / "remotion.config.ts").write_text(REMOTION_CONFIG, encoding="utf-8")
        (self.root / "tsconfig.json").write_text(TSCONFIG, encoding="utf-8")
        (self.src / "index.ts").write_text(INDEX_TS, encoding="utf-8")

    @staticmethod
    def package_json() -> str:
        return json.dumps(
            {"name": "vibemotion-project", "version": "1.0.0", "private": True,
             "dependencies": package_json_dependencies()},
            indent=2,
        ) + "\n"

    def write_files(self) -> None:
        self.write_scaffold()
        keep = set()
        for it in self.items:
            f = self.comp_dir / f"{it.id}.tsx"
            if not f.exists() or f.read_text(encoding="utf-8") != it.code:
                atomic_write(f, it.code)
            keep.add(f.name)
        for stale in self.comp_dir.glob("*.tsx"):
            if stale.name not in keep:
                stale.unlink()
        root = self.root_tsx()
        target = self.src / "Root.tsx"
        if not target.exists() or target.read_text(encoding="utf-8") != root:
            atomic_write(target, root)

    @staticmethod
    def _audio_wrapper(it: VideoItem) -> str:
        """Komponen pembungkus: komposisi asli + <Audio> (musik dengan fade, voice-over penuh). Tanpa mengubah kode AI."""
        frames = it.frames
        fade_in = min(30, max(1, frames // 4))
        out_start = max(fade_in + 1, frames - 45)
        out_end = max(out_start + 1, frames)
        tracks = []
        if it.music:
            v = round(it.music_volume, 3)
            tracks.append(
                f"      <Audio src={{staticFile({json.dumps(it.music)})}} loop volume={{(f) => interpolate(f, "
                f"[0, {fade_in}, {out_start}, {out_end}], [0, {v}, {v}, 0], "
                f"{{ extrapolateLeft: \"clamp\", extrapolateRight: \"clamp\" }})}} />")
        if it.voiceover:
            tracks.append(f"      <Audio src={{staticFile({json.dumps(it.voiceover)})}} />")
        body = "\n".join(tracks)
        return (f"const W_{it.id}: React.FC = () => (\n  <AbsoluteFill>\n    <C_{it.id} />\n{body}\n  </AbsoluteFill>\n);\n")

    def root_tsx(self) -> str:
        imports = "\n".join(
            f'import {{ Remotion as C_{i.id} }} from "./compositions/{i.id}";' for i in self.items
        )
        wrapped = [i for i in self.items if i.has_audio]
        wrappers = ("\n" + "\n".join(self._audio_wrapper(i) for i in wrapped)) if wrapped else ""
        names = "AbsoluteFill, Audio, Composition, interpolate, staticFile" if wrapped else "Composition"
        comps = "\n".join(
            f'      <Composition id="{i.comp_id}" component={{{("W_" if i.has_audio else "C_") + i.id} as React.ComponentType<any>}} '
            f"durationInFrames={{{i.frames}}} fps={{{i.fps}}} width={{{i.width}}} height={{{i.height}}} />"
            for i in self.items
        )
        return (
            f'import React from "react";\nimport {{ {names} }} from "remotion";\n{imports}\n{wrappers}\n'
            f"export const RemotionRoot: React.FC = () => {{\n  return (\n    <>\n{comps}\n    </>\n  );\n}};\n"
        )

    def import_asset(self, path: Path) -> str:
        """Salin berkas ke public/assets dan kembalikan path untuk staticFile()."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        dest = self.assets_dir / Path(path).name
        dest.write_bytes(Path(path).read_bytes())
        return f"assets/{dest.name}"

    def write_captions(self, captions: list[dict], stem: str = "captions") -> str:
        """Simpan caption JSON ke public/assets dan kembalikan path untuk staticFile()."""
        from .code_utils import safe_filename
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        name = f"{safe_filename(stem, 'captions')}.json"
        atomic_write(self.assets_dir / name, json.dumps(captions, ensure_ascii=False, indent=2))
        return f"assets/{name}"

    def list_assets(self) -> list[str]:
        if not self.assets_dir.exists():
            return []
        return sorted(f"assets/{p.name}" for p in self.assets_dir.iterdir() if p.is_file())


REMOTION_CONFIG = '''import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("png");
Config.setPixelFormat("yuv420p");
Config.setOverwriteOutput(true);
'''

TSCONFIG = '''{
  "compilerOptions": {
    "target": "ES2020", "module": "ESNext", "moduleResolution": "Bundler",
    "jsx": "react-jsx", "strict": false, "skipLibCheck": true, "noEmit": true,
    "esModuleInterop": true, "resolveJsonModule": true
  },
  "include": ["src"]
}
'''

INDEX_TS = '''import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
'''

__all__ = ["Project", "VideoItem", "PLACEHOLDER_CODE", "REMOTION_VERSION"]
