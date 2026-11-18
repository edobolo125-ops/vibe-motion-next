"""Alur AI lanjutan: koreksi otomatis, tinjauan visual, storyboard, transkripsi."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.validate import Issue, issues_to_text
from .base import AIError
from .prompts import GenerationSpec
from .service import AIService

Status = Callable[[str], None]
Validator = Callable[[str], list[Issue]]


def extract_json(text: str):
    """Ambil JSON pertama (objek/array) dari balasan AI, walau dibungkus ``` atau teks lain."""
    t = re.sub(r"```(?:json)?", "", text).strip()
    # coba pembuka yang muncul lebih dulu (objek luar sebelum array di dalamnya)
    for opener, closer in sorted((("[", "]"), ("{", "}")), key=lambda oc: (t.find(oc[0]) == -1, t.find(oc[0]))):
        a, b = t.find(opener), t.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except ValueError:
                continue
    raise AIError("Balasan AI bukan JSON yang valid.")


# ---------- 1. generate + koreksi otomatis ----------
def generate_checked(svc: AIService, spec: GenerationSpec, instruction: str, images: list[Path] | None,
                     validator: Validator, max_fixes: int = 2, on_status: Status = lambda _s: None
                     ) -> tuple[str, list[Issue]]:
    code = svc.generate(spec, instruction, images)
    for n in range(max_fixes):
        issues = validator(code)
        if not issues:
            return code, []
        on_status(f"Memperbaiki otomatis ({n + 1}/{max_fixes})…")
        try:
            code = svc.fix(code, issues_to_text(issues))
        except AIError:
            break  # perbaikan gagal: pakai kode terakhir yang ada
    return code, validator(code)


# ---------- 2. tinjauan visual ----------
REVIEW_SYSTEM = (
    "Kamu reviewer motion graphic. Kamu diberi gambar PERTAMA = frame hasil render, dan (jika ada) gambar berikutnya = "
    "referensi. Nilai apakah frame sesuai permintaan: teks terpotong/keluar layar, elemen menumpuk, kontras buruk, "
    "kanvas kosong/hitam, atau jauh dari referensi. Balas HANYA JSON: "
    '{"ok": true|false, "problems": ["masalah konkret dan cara memperbaikinya", ...]}. '
    "Jika layak, ok=true dan problems kosong. Jangan terlalu perfeksionis."
)


def review_visual(svc: AIService, still: Path, instruction: str, refs: list[Path] | None = None) -> tuple[bool, str]:
    try:
        raw = svc.provider.complete(REVIEW_SYSTEM, f"PERMINTAAN ASLI:\n{instruction}", [still, *(refs or [])])
        data = extract_json(raw)
    except AIError:
        return True, ""  # tinjauan gagal ≠ kode salah; jangan menahan hasil
    ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
    problems = data.get("problems", []) if isinstance(data, dict) else []
    return ok or not problems, "\n".join(f"- {p}" for p in problems)


def generate_reviewed(svc: AIService, spec: GenerationSpec, instruction: str, images: list[Path] | None,
                      validator: Validator, still_renderer: Callable[[str], Path], max_rounds: int = 1,
                      on_status: Status = lambda _s: None) -> tuple[str, list[Issue]]:
    code, issues = generate_checked(svc, spec, instruction, images, validator, on_status=on_status)
    for n in range(max_rounds):
        if issues:
            break  # masih ada error teknis: render pasti gagal, lewati tinjauan visual
        on_status(f"Tinjauan visual ({n + 1}/{max_rounds})…")
        try:
            ok, problems = review_visual(svc, still_renderer(code), instruction, images)
        except Exception:  # noqa: BLE001 — render still gagal (mis. Chrome belum ada): lewati
            break
        if ok:
            break
        on_status("Memperbaiki masalah visual…")
        try:
            fixed = svc.fix(code, "Masalah visual pada frame hasil render:\n" + problems)
        except AIError:
            break
        new_issues = validator(fixed)
        if new_issues:
            break  # jangan ganti kode yang sehat dengan yang rusak
        code = fixed
    return code, issues


# ---------- 3. storyboard ----------
@dataclass
class Scene:
    title: str
    brief: str
    seconds: float


PLAN_SYSTEM = (
    "Kamu sutradara motion graphic. Pecah ide user menjadi adegan berurutan yang saling nyambung (hook → isi → penutup). "
    'Balas HANYA JSON array: [{"title": "...", "brief": "deskripsi visual & teks yang tampil, 1-3 kalimat", "seconds": angka}]. '
    "Jumlah adegan PERSIS sesuai permintaan."
)


def plan_scenes(svc: AIService, instruction: str, n: int, total_seconds: float) -> list[Scene]:
    n = max(2, min(12, n))
    raw = svc.provider.complete(PLAN_SYSTEM, f"IDE:\n{instruction}\n\nJumlah adegan: {n}\nTotal durasi: {total_seconds:g} detik")
    data = extract_json(raw)
    if not isinstance(data, list) or not data:
        raise AIError("Rencana adegan tidak valid.")
    scenes = []
    for item in data[:n]:
        if not isinstance(item, dict):
            continue
        try:
            secs = float(item.get("seconds", total_seconds / n))
        except (TypeError, ValueError):
            secs = total_seconds / n
        scenes.append(Scene(str(item.get("title", f"Adegan {len(scenes) + 1}"))[:60],
                            str(item.get("brief", "")), max(1.0, secs)))
    if not scenes:
        raise AIError("Rencana adegan tidak valid.")
    scale = total_seconds / sum(s.seconds for s in scenes)  # normalkan agar jumlah = total
    for s in scenes:
        s.seconds = round(max(1.0, s.seconds * scale), 1)
    return scenes


def scene_instruction(scene: Scene, idx: int, total: int, idea: str) -> str:
    return (f"Ini adegan {idx} dari {total} dalam satu video berurutan. Pertahankan gaya, palet, dan tipografi yang konsisten.\n"
            f"IDE KESELURUHAN: {idea}\nADEGAN {idx}: {scene.title}\n{scene.brief}")


# ---------- 4. transkripsi (Gemini) ----------
TRANSCRIBE_SYSTEM = (
    "Transkripsikan audio persis seperti diucapkan, dalam bahasa aslinya. Balas HANYA JSON array: "
    '[{"start": detik, "end": detik, "text": "kalimat"}]. Satu entri per kalimat/frasa pendek (maks ±12 kata), '
    "waktu dalam detik (desimal), urut, tidak tumpang tindih. Jangan meringkas."
)
MAX_INLINE_MB = 18


def transcribe(svc: AIService, media: Path) -> list[dict]:
    from .gemini import GeminiProvider
    if not isinstance(svc.provider, GeminiProvider):
        raise AIError("Transkripsi audio hanya tersedia dengan provider Gemini. Ganti provider di Pengaturan.")
    if Path(media).stat().st_size > MAX_INLINE_MB * 1024 * 1024:
        raise AIError(f"File terlalu besar (maks {MAX_INLINE_MB} MB). Potong atau kompres audionya dulu.")
    data = extract_json(svc.provider.complete(TRANSCRIBE_SYSTEM, "Transkripsikan.", [Path(media)]))
    caps = []
    for c in data if isinstance(data, list) else []:
        try:
            start, end, text = float(c["start"]), float(c["end"]), str(c["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if text and end > start >= 0:
            caps.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    if not caps:
        raise AIError("Tidak ada ucapan yang terdeteksi.")
    return sorted(caps, key=lambda c: c["start"])


# ---------- 5. edit divalidasi + adaptasi rasio ----------
def edit_checked(svc: AIService, code: str, request: str, spec: GenerationSpec | None, validator: Validator,
                 max_fixes: int = 2, on_status: Status = lambda _s: None) -> tuple[str, list[Issue]]:
    """Edit dengan AI, lalu validasi & perbaiki otomatis seperti pada generate."""
    new = svc.edit(code, request, spec)
    for n in range(max_fixes):
        issues = validator(new)
        if not issues:
            return new, []
        on_status(f"Memperbaiki otomatis ({n + 1}/{max_fixes})…")
        try:
            new = svc.fix(new, issues_to_text(issues))
        except AIError:
            break
    return new, validator(new)


ADAPT_REQUEST = (
    "Adaptasikan layout video ini dari {fw}x{fh} ke {tw}x{th} (rasio berbeda). Atur ulang ukuran font, posisi, jarak, "
    "dan tata letak agar tetap proporsional dan tidak ada yang terpotong atau keluar layar. Gunakan useVideoConfig() "
    "untuk ukuran. Jangan ubah isi teks, warna utama, maupun gaya animasinya."
)


def adapt_ratio(svc: AIService, code: str, src: tuple[int, int], dst: tuple[int, int], spec: GenerationSpec | None,
                validator: Validator, on_status: Status = lambda _s: None) -> tuple[str, list[Issue]]:
    req = ADAPT_REQUEST.format(fw=src[0], fh=src[1], tw=dst[0], th=dst[1])
    return edit_checked(svc, code, req, spec, validator, on_status=on_status)


VARIATION_REQUEST = (
    "Buat VARIASI ke-{n} dari video ini: ubah dengan jelas palet warna, tata letak, dan gaya animasi sehingga terlihat "
    "berbeda dari versi sekarang, tetapi isi/teks dan durasi tetap sama. Variasi ini harus berbeda dari variasi lain."
)
