"""Prompt sistem — teks bersih ditulis ulang, bukan salinan dari aplikasi lama."""
from __future__ import annotations

from dataclasses import dataclass, field

STYLE_OPTIONS = {
    "entrance": ["Auto", "Spring pop", "Fade & slide", "Typewriter", "Zoom blur", "Stagger reveal"],
    "camera": ["Auto", "Static", "Slow zoom in", "Parallax drift", "Handheld shake"],
    "pacing": ["Auto", "Calm", "Medium", "Fast & punchy"],
    "complexity": ["Auto", "Simple", "Moderate", "Rich / layered"],
    "art_style": ["Auto", "Minimal flat", "Glassmorphism", "Neon cyberpunk", "3D soft", "Retro / pop-art"],
    "typography": ["Auto", "Bold sans-serif", "Elegant serif", "Monospace tech", "Handwritten"],
    "palette": ["Auto", "Dark + accent", "Pastel", "Monochrome", "Vibrant gradient"],
    "lighting": ["Auto", "None", "Soft glow", "Neon bloom", "Spotlight"],
}


@dataclass
class GenerationSpec:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration_sec: float = 10.0
    theme: str = ""
    styles: dict[str, str] = field(default_factory=dict)
    assets: list[str] = field(default_factory=list)  # path untuk staticFile()
    extra: str = ""

    @property
    def frames(self) -> int:
        return max(1, round(self.duration_sec * self.fps))


BASE_RULES = """Kamu adalah engineer motion graphic ahli Remotion (React + TypeScript).
Tugas: menulis SATU komponen video Remotion.

ATURAN OUTPUT (wajib):
1. Balas HANYA kode TSX mentah. Tanpa markdown, tanpa penjelasan.
2. Ekspor bernama: `export const Remotion: React.FC = () => { ... }`.
3. Mulai dengan `import React from "react";` lalu impor dari "remotion" seperlunya
   (AbsoluteFill, Sequence, Series, Img, Video, Audio, interpolate, spring, useCurrentFrame, useVideoConfig, staticFile).
4. Ukuran, fps, dan durasi diambil dari useVideoConfig(); jangan hardcode ukuran kanvas.
5. Semua animasi dihitung dari frame (interpolate/spring). Dilarang CSS transition, setTimeout, Math.random() tanpa seed.
6. Aset lokal hanya lewat staticFile("assets/<nama>"). Jika <Video> dan <Audio> dipakai bersamaan, beri <Video muted />.
7. Pastikan semua tag JSX dan kurung tertutup. Hanya gunakan paket yang sudah terpasang.
"""

CAPTION_RULES = """ATURAN CAPTION: masukkan SELURUH kalimat dari data JSON ke dalam satu array konstanta.
Jangan membuat <Sequence> per kalimat; cari caption aktif dengan
`const t = frame / fps; const cap = captions.find(c => t >= c.start && t < c.end);`.
"""


def build_system_prompt(spec: GenerationSpec, skills: str = "") -> str:
    styles = "\n".join(f"- {k}: {v}" for k, v in spec.styles.items() if v and v != "Auto")
    assets = "\n".join(f'- staticFile("{a}")' for a in spec.assets) or "(tidak ada)"
    return (
        f"{BASE_RULES}\nSPESIFIKASI VIDEO: {spec.width}x{spec.height}px, {spec.fps} fps, "
        f"{spec.duration_sec:g} detik ({spec.frames} frame).\n"
        + (f"TEMA: {spec.theme}\n" if spec.theme else "")
        + (f"GAYA:\n{styles}\n" if styles else "")
        + f"ASET LOKAL TERSEDIA:\n{assets}\n"
        + (f"\n{CAPTION_RULES}" if any("caption" in a.lower() or a.endswith(".json") for a in spec.assets) else "")
        + (f"\nINSTRUKSI TAMBAHAN: {spec.extra}\n" if spec.extra else "")
        + skills
    )


EDIT_RULES = """Kamu mengedit komponen Remotion yang sudah ada. Terapkan permintaan user dan kembalikan
KODE LENGKAP hasil akhir (bukan potongan/diff). Pertahankan `export const Remotion`. Balas HANYA TSX mentah."""

FIX_RULES = """Kode Remotion di bawah gagal dikompilasi / dirender. Perbaiki error yang diberikan seminimal mungkin
tanpa mengubah desain. Pastikan impor benar, tag JSX tertutup, dan `export const Remotion` ada.
Balas HANYA TSX mentah lengkap."""
