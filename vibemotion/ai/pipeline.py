"""Alur pembuatan video dari awal sampai masuk proyek: satu video / variasi / storyboard, dengan
validasi + perbaikan otomatis dan (opsional) tinjauan visual. Tanpa UI, jadi bisa diuji."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from ..core.project import PLACEHOLDER_CODE, Project, VideoItem
from ..core.render import render_still
from ..core.validate import Issue, check_code
from .extras import (VARIATION_REQUEST, Scene, adapt_ratio, edit_checked, generate_checked, generate_reviewed,
                     plan_scenes, scene_instruction)
from .prompts import GenerationSpec
from .service import AIService

Status = Callable[[str], None]
StillRenderer = Callable[[Project, VideoItem, Path], Path]


def default_still(extra_args: list[str] | None = None) -> StillRenderer:
    return lambda project, item, out: render_still(project, item, out, extra_args=extra_args)


def make_validator(project: Project, enabled: bool) -> Callable[[str], list[Issue]]:
    if not enabled:
        return lambda _code: []
    return lambda code: check_code(code, project.root)


def _one(svc: AIService, project: Project, item: VideoItem, spec: GenerationSpec, instruction: str,
         images: list[Path] | None, validator, visual: bool, still: StillRenderer, status: Status) -> list[Issue]:
    """Bangun satu video. `item` sengaja TIDAK ada di daftar proyek selama AI bekerja (bisa menit-menit), jadi tidak
    bisa dihapus/dipilih setengah jadi dari bagian UI lain. Ia baru masuk (`attach`) setelah kodenya jadi."""
    if visual:
        def render_candidate(code: str) -> Path:
            item.code = code
            project.attach(item)  # render butuh video ada di Root.tsx; bila gagal, build() menariknya lagi
            project.save()
            return still(project, item, project.root / ".vm_review" / f"{item.id}.png")
        code, issues = generate_reviewed(svc, spec, instruction, images, validator, render_candidate, on_status=status)
    else:
        code, issues = generate_checked(svc, spec, instruction, images, validator, on_status=status)
    item.code = code
    project.attach(item)
    project.save()
    project.history.snapshot(item.id, item.code, "AI generate")  # lewat objek sendiri, bukan pencarian di daftar
    return issues


def generate_videos(svc: AIService, project: Project, spec: GenerationSpec, instruction: str,
                    images: list[Path] | None = None, *, mode: str = "single", count: int = 1, scenes: int = 3,
                    merge: bool = True, auto_check: bool = True, visual_review: bool = False,
                    status: Status = lambda _s: None, still: StillRenderer | None = None, label: str = ""
                    ) -> tuple[list[VideoItem], list[str]]:
    """Kembalikan (video baru, catatan masalah tersisa). Item gagal dibuang; yang sudah jadi dipertahankan."""
    validator = make_validator(project, auto_check)
    still = still or default_still()
    made: list[VideoItem] = []
    notes: list[str] = []

    def build(name: str, sp: GenerationSpec, instr: str) -> None:
        item = project.detached(PLACEHOLDER_CODE, name, width=sp.width, height=sp.height, fps=sp.fps,
                                duration_sec=sp.duration_sec)
        try:
            issues = _one(svc, project, item, sp, instr, images, validator, visual_review, still, status)
        except Exception:
            project.remove(item.id)  # bila sempat masuk (jalur tinjauan visual); juga melepas id yang dipesan
            project.save()
            raise
        made.append(item)
        if issues:
            notes.append(f"{name}: " + "; ".join(str(i) for i in issues))

    if mode == "storyboard":
        status("Merencanakan adegan…")
        plan: list[Scene] = plan_scenes(svc, instruction, scenes, spec.duration_sec)
        for i, sc in enumerate(plan, 1):
            status(f"Adegan {i}/{len(plan)}: {sc.title}")
            build(sc.title + (f" · {label}" if label else ""), replace(spec, duration_sec=sc.seconds), scene_instruction(sc, i, len(plan), instruction))
        if merge and len(made) >= 2:
            try:
                merged = project.merge([m.id for m in made if project.contains(m.id)], "Storyboard")
                project.save()
                made.append(merged)
            except (KeyError, ValueError):
                notes.append("Gabungan storyboard dilewati: ada adegan yang sudah dihapus.")
    else:
        for n in range(max(1, count)):
            status(f"Video {n + 1}/{count}")
            build(f"Video {len(project.items) + 1}" + (f" · {label}" if label else ""), spec, instruction)
    return made, notes


def make_variations(svc: AIService, project: Project, video_id: str, n: int, *, auto_check: bool = True,
                    status: Status = lambda _s: None) -> tuple[list[VideoItem], list[str]]:
    """Buat n variasi dari satu video (edit AI + validasi). Item gagal dibuang."""
    src = project.get(video_id)
    validator = make_validator(project, auto_check)
    spec = GenerationSpec(width=src.width, height=src.height, fps=src.fps, duration_sec=src.duration_sec,
                          assets=project.list_assets())
    made: list[VideoItem] = []
    notes: list[str] = []
    for i in range(1, max(1, min(6, n)) + 1):
        status(f"Variasi {i}/{n}")
        item = project.detached(src.code, f"{src.name} · var {i}", width=src.width, height=src.height, fps=src.fps,
                                duration_sec=src.duration_sec, music=src.music, music_volume=src.music_volume,
                                voiceover=src.voiceover)
        try:
            code, issues = edit_checked(svc, src.code, VARIATION_REQUEST.format(n=i), spec, validator, on_status=status)
        except Exception:
            project.release(item.id)
            raise
        item.code = code
        project.attach(item)
        project.save()
        project.history.snapshot(item.id, item.code, "AI variasi")
        made.append(item)
        if issues:
            notes.append(f"{item.name}: " + "; ".join(str(x) for x in issues))
    return made, notes


def make_ratio_variants(svc: AIService | None, project: Project, video_id: str, ratios: dict[str, tuple[int, int]],
                        *, adapt_with_ai: bool = False, auto_check: bool = True,
                        status: Status = lambda _s: None) -> tuple[list[VideoItem], list[str]]:
    """Varian rasio: salin dulu; bila adapt_with_ai, tiap salinan di-layout ulang oleh AI (gagal → tetap salinan)."""
    src = project.get(video_id)
    items = project.variants(video_id, ratios)
    notes: list[str] = []
    if adapt_with_ai and svc is not None:
        validator = make_validator(project, auto_check)
        project.save()
        for it in items:
            status(f"Adaptasi layout {it.width}x{it.height}…")
            spec = GenerationSpec(width=it.width, height=it.height, fps=it.fps, duration_sec=it.duration_sec,
                                  assets=project.list_assets())
            try:
                code, issues = adapt_ratio(svc, src.code, (src.width, src.height), (it.width, it.height), spec, validator,
                                           on_status=status)
                it.code = code
                if issues:
                    notes.append(f"{it.name}: " + "; ".join(str(x) for x in issues))
            except Exception as e:  # noqa: BLE001 — satu rasio gagal tidak membatalkan yang lain
                notes.append(f"{it.name}: adaptasi AI gagal ({e}); dipakai salinan asli")
    project.save()
    return items, notes
