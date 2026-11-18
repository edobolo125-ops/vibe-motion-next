"""Template TSX bawaan. Ukuran mengikuti useVideoConfig(), teks/warna di konstanta atas supaya mudah diubah."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    key: str
    label_id: str
    label_en: str
    seconds: float
    code: str


INTRO = '''import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const TITLE = "JUDUL VIDEO";
const SUBTITLE = "Subjudul singkat di sini";
const BG_A = "#0f172a";
const BG_B = "#312e81";
const ACCENT = "#38bdf8";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const pop = spring({ frame: frame - 6, fps, config: { damping: 12, stiffness: 120 } });
  const sub = spring({ frame: frame - 22, fps, config: { damping: 200 } });
  const line = interpolate(frame, [10, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const out = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  const angle = interpolate(frame, [0, durationInFrames], [135, 200]);
  return (
    <AbsoluteFill style={{ background: `linear-gradient(${angle}deg, ${BG_A}, ${BG_B})`, justifyContent: "center", alignItems: "center", opacity: out }}>
      <div style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 800, color: "#fff", fontSize: s * 0.11, letterSpacing: s * 0.004,
        textAlign: "center", transform: `scale(${0.6 + 0.4 * pop})`, opacity: pop, padding: "0 6%" }}>{TITLE}</div>
      <div style={{ height: s * 0.008, width: width * 0.4 * line, background: ACCENT, margin: `${s * 0.03}px 0`, borderRadius: 99 }} />
      <div style={{ fontFamily: "Inter, Arial, sans-serif", color: "#cbd5e1", fontSize: s * 0.04, opacity: sub, transform: `translateY(${(1 - sub) * 30}px)`, textAlign: "center", padding: "0 8%" }}>{SUBTITLE}</div>
    </AbsoluteFill>
  );
};
'''

LOWER_THIRD = '''import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const NAME = "Nama Lengkap";
const ROLE = "Jabatan / Keterangan";
const BAR = "#f59e0b";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const inn = spring({ frame, fps, config: { damping: 18 } });
  const out = interpolate(frame, [durationInFrames - 18, durationInFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const x = (1 - inn) * -width * 0.5 - out * width * 0.5;
  return (
    <AbsoluteFill style={{ background: "#111827", justifyContent: "flex-end", padding: `0 ${width * 0.06}px ${height * 0.12}px` }}>
      <div style={{ display: "flex", alignItems: "stretch", transform: `translateX(${x}px)` }}>
        <div style={{ width: s * 0.012, background: BAR, borderRadius: 4 }} />
        <div style={{ background: "rgba(0,0,0,0.65)", padding: `${s * 0.02}px ${s * 0.035}px`, fontFamily: "Inter, Arial, sans-serif" }}>
          <div style={{ color: "#fff", fontWeight: 800, fontSize: s * 0.055 }}>{NAME}</div>
          <div style={{ color: BAR, fontWeight: 500, fontSize: s * 0.032, marginTop: s * 0.006 }}>{ROLE}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
'''

COUNTDOWN = '''import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

const START = 5;
const COLOR = "#22d3ee";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const s = Math.min(width, height);
  const sec = Math.min(START - 1, Math.floor(frame / fps));
  const n = START - sec;
  const local = (frame % fps) / fps;
  const scale = interpolate(local, [0, 0.25, 1], [1.5, 1, 0.9]);
  const opacity = interpolate(local, [0, 0.12, 0.85, 1], [0, 1, 1, 0.4]);
  const r = s * 0.28;
  const circ = 2 * Math.PI * r;
  return (
    <AbsoluteFill style={{ background: "#020617", justifyContent: "center", alignItems: "center" }}>
      <svg width={r * 2.6} height={r * 2.6} viewBox={`${-r * 1.3} ${-r * 1.3} ${r * 2.6} ${r * 2.6}`} style={{ position: "absolute" }}>
        <circle r={r} fill="none" stroke="#1e293b" strokeWidth={s * 0.015} />
        <circle r={r} fill="none" stroke={COLOR} strokeWidth={s * 0.015} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={circ * local} transform="rotate(-90)" />
      </svg>
      <div style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 900, fontSize: s * 0.32, color: "#fff", transform: `scale(${scale})`, opacity }}>{n}</div>
    </AbsoluteFill>
  );
};
'''

KINETIC = '''import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const WORDS = ["BUAT", "VIDEO", "KEREN", "DENGAN", "KODE"];
const COLORS = ["#f472b6", "#fbbf24", "#34d399", "#60a5fa", "#a78bfa"];
const PER_WORD = 12; // frame antar kata

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const out = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  return (
    <AbsoluteFill style={{ background: "#09090b", justifyContent: "center", alignItems: "center", opacity: out }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: s * 0.01 }}>
        {WORDS.map((w, i) => {
          const p = spring({ frame: frame - i * PER_WORD, fps, config: { damping: 11, stiffness: 160 } });
          return (
            <div key={w + i} style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 900, fontSize: s * 0.12, lineHeight: 1,
              color: COLORS[i % COLORS.length], opacity: Math.min(1, p * 1.5), transform: `translateY(${(1 - p) * 60}px) scale(${0.7 + 0.3 * p})`,
              letterSpacing: s * 0.003 }}>{w}</div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
'''

QUOTE = """import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const QUOTE = "Kreativitas adalah kecerdasan yang sedang bersenang-senang.";
const AUTHOR = "Albert Einstein";
const BG = "#faf5ee";
const INK = "#1f2937";
const ACCENT = "#e11d48";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const words = QUOTE.split(" ");
  const out = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  const mark = spring({ frame, fps, config: { damping: 14 } });
  const author = spring({ frame: frame - (8 + words.length * 4), fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", padding: "0 9%", opacity: out }}>
      <div style={{ fontFamily: "Georgia, serif", color: ACCENT, fontSize: s * 0.28, lineHeight: 0.6, height: s * 0.12, transform: `scale(${mark})`, opacity: mark }}>“</div>
      <div style={{ fontFamily: "Georgia, serif", color: INK, fontSize: s * 0.065, lineHeight: 1.25, textAlign: "center", fontWeight: 700 }}>
        {words.map((w, i) => {
          const p = spring({ frame: frame - (6 + i * 4), fps, config: { damping: 20 } });
          return <span key={i} style={{ display: "inline-block", marginRight: s * 0.018, opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>{w}</span>;
        })}
      </div>
      <div style={{ marginTop: s * 0.04, fontFamily: "Inter, Arial, sans-serif", color: INK, fontSize: s * 0.034, letterSpacing: s * 0.004, opacity: author * 0.75 }}>— {AUTHOR}</div>
    </AbsoluteFill>
  );
};
"""

STAT = """import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const VALUE = 2500000;
const PREFIX = "";
const SUFFIX = "+";
const LABEL = "Pengguna aktif";
const BG = "#0b1220";
const COLOR = "#34d399";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const count = spring({ frame: frame - 6, fps, durationInFrames: Math.max(30, durationInFrames - 30), config: { damping: 200 } });
  const shown = Math.round(VALUE * count).toLocaleString("id-ID");
  const bar = interpolate(count, [0, 1], [0, 1]);
  const label = spring({ frame: frame - 20, fps, config: { damping: 200 } });
  const out = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  return (
    <AbsoluteFill style={{ background: BG, justifyContent: "center", alignItems: "center", opacity: out }}>
      <div style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 900, color: "#fff", fontSize: s * 0.15, letterSpacing: -s * 0.003 }}>
        <span style={{ color: COLOR }}>{PREFIX}</span>{shown}<span style={{ color: COLOR }}>{SUFFIX}</span>
      </div>
      <div style={{ width: width * 0.5, height: s * 0.012, background: "#1f2a44", borderRadius: 99, margin: `${s * 0.04}px 0` }}>
        <div style={{ width: `${bar * 100}%`, height: "100%", background: COLOR, borderRadius: 99 }} />
      </div>
      <div style={{ fontFamily: "Inter, Arial, sans-serif", color: "#94a3b8", fontSize: s * 0.04, opacity: label, transform: `translateY(${(1 - label) * 20}px)` }}>{LABEL}</div>
    </AbsoluteFill>
  );
};
"""

LOGO = """import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const BRAND = "NOVA";
const TAGLINE = "Ide menjadi gerak";
const BG = "#05060a";
const ACCENT = "#a78bfa";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const letters = BRAND.split("");
  const line = interpolate(frame, [4, 28], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const tag = spring({ frame: frame - 14 - letters.length * 5, fps, config: { damping: 200 } });
  const glow = 0.5 + 0.5 * Math.sin(frame / 12);
  const out = interpolate(frame, [durationInFrames - 15, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  return (
    <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 50%, #151a33 0%, ${BG} 70%)`, justifyContent: "center", alignItems: "center", opacity: out }}>
      <div style={{ display: "flex", gap: s * 0.02 }}>
        {letters.map((l, i) => {
          const p = spring({ frame: frame - 10 - i * 5, fps, config: { damping: 14, stiffness: 140 } });
          return (
            <div key={i} style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 900, fontSize: s * 0.2, color: "#fff", opacity: p,
              transform: `translateY(${(1 - p) * 60}px) scale(${0.8 + 0.2 * p})`, textShadow: `0 0 ${20 + glow * 30}px ${ACCENT}` }}>{l}</div>
          );
        })}
      </div>
      <div style={{ height: s * 0.006, width: width * 0.32 * line, background: ACCENT, borderRadius: 99, margin: `${s * 0.035}px 0` }} />
      <div style={{ fontFamily: "Inter, Arial, sans-serif", color: "#cbd5e1", fontSize: s * 0.04, letterSpacing: s * 0.01, opacity: tag }}>{TAGLINE.toUpperCase()}</div>
    </AbsoluteFill>
  );
};
"""

BARS = """import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

const TITLE = "Penjualan per kuartal";
const DATA = [
  { label: "Q1", value: 42 },
  { label: "Q2", value: 68 },
  { label: "Q3", value: 55 },
  { label: "Q4", value: 90 },
];
const COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#f472b6"];
const BG = "#0f172a";

export const Remotion: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const s = Math.min(width, height);
  const max = Math.max(...DATA.map((d) => d.value));
  const chartH = height * 0.5;
  const title = spring({ frame, fps, config: { damping: 200 } });
  const out = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center", opacity: out }}>
      <div style={{ fontFamily: "Inter, Arial, sans-serif", fontWeight: 800, color: "#fff", fontSize: s * 0.055, marginBottom: s * 0.05, opacity: title }}>{TITLE}</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: width * 0.04, height: chartH }}>
        {DATA.map((d, i) => {
          const p = spring({ frame: frame - 8 - i * 6, fps, config: { damping: 18 } });
          const h = (d.value / max) * chartH * p;
          return (
            <div key={d.label} style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%" }}>
              <div style={{ fontFamily: "Inter, Arial, sans-serif", color: "#fff", fontWeight: 700, fontSize: s * 0.035, marginBottom: 8, opacity: p }}>{Math.round(d.value * p)}</div>
              <div style={{ width: width * 0.12, height: h, background: COLORS[i % COLORS.length], borderRadius: `${s * 0.012}px ${s * 0.012}px 0 0` }} />
              <div style={{ fontFamily: "Inter, Arial, sans-serif", color: "#94a3b8", fontSize: s * 0.03, marginTop: 10 }}>{d.label}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
"""

TEMPLATES: dict[str, Template] = {t.key: t for t in [
    Template("intro", "Intro judul", "Title intro", 5, INTRO),
    Template("lower_third", "Lower third (nama + jabatan)", "Lower third (name + role)", 5, LOWER_THIRD),
    Template("countdown", "Hitung mundur", "Countdown", 5, COUNTDOWN),
    Template("kinetic", "Teks kinetik", "Kinetic text", 6, KINETIC),
    Template("quote", "Kutipan", "Quote", 7, QUOTE),
    Template("stat", "Statistik (angka naik)", "Stat counter", 5, STAT),
    Template("logo", "Logo reveal (teks)", "Logo reveal (text)", 5, LOGO),
    Template("bars", "Grafik batang", "Bar chart", 6, BARS),
]}
