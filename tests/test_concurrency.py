import threading

import pytest

from vibemotion.ai.pipeline import generate_videos, make_variations
from vibemotion.ai.prompts import GenerationSpec
from vibemotion.ai.service import AIService
from vibemotion.core.project import Project

GOOD = "export const Remotion = () => null;"


class Provider:
    """AI palsu yang menjalankan `during` di tengah generasi — meniru pengguna/thread lain yang mengutak-atik proyek
    selagi AI bekerja berjam-menit."""
    def __init__(self, during=None): self.during, self.calls = during, 0
    def complete(self, system, user, images=None):
        self.calls += 1
        if self.during: self.during()
        return GOOD


def svc(during=None): return AIService(Provider(during), skills_loader=lambda: "")


def test_regression_user_removes_or_reloads_items_while_ai_is_working(tmp_path):
    """Regresi dari log nyata: KeyError: 'scene_007' di pipeline._one → project.snapshot → project.get."""
    p = Project(tmp_path); p.add(name="Awal")
    def meddle():
        for it in list(p.items): p.remove(it.id)   # semua video (termasuk yang sedang dibuat, bila terlihat) dihapus
    items, notes = generate_videos(svc(meddle), p, GenerationSpec(), "x", auto_check=False)
    assert len(items) == 1 and items[0].code.endswith(GOOD + "\n")  # tidak crash: hasil AI tetap masuk proyek
    assert any(i.id == items[0].id for i in p.items)
    assert (tmp_path / "src/compositions" / f"{items[0].id}.tsx").exists()


def test_pending_video_is_not_visible_in_project_during_generation(tmp_path):
    p = Project(tmp_path); p.add(name="Awal")
    seen = []
    items, _ = generate_videos(svc(lambda: seen.append([i.id for i in p.items])), p, GenerationSpec(), "x", auto_check=False)
    assert seen == [["scene_001"]]  # video yang sedang dibuat tidak muncul (tidak bisa dihapus/dipilih setengah jadi)
    assert [i.id for i in p.items] == ["scene_001", items[0].id]


def test_ids_reserved_for_pending_video_are_never_reused(tmp_path):
    p = Project(tmp_path); p.add(name="Awal")
    added = []
    items, _ = generate_videos(svc(lambda: added.append(p.add(name="dari pengguna"))), p, GenerationSpec(), "x", auto_check=False)
    ids = [i.id for i in p.items]
    assert len(ids) == len(set(ids)) == 3 and items[0].id != added[0].id  # tabrakan id tidak mungkin terjadi


def test_failed_generation_leaves_no_trace(tmp_path):
    from vibemotion.ai.base import AIError
    p = Project(tmp_path); p.add(name="Awal")
    class Boom:
        def complete(self, *a, **k): raise AIError("503")
    with pytest.raises(AIError):
        generate_videos(AIService(Boom(), skills_loader=lambda: ""), p, GenerationSpec(), "x", auto_check=False)
    assert [i.id for i in p.items] == ["scene_001"]
    nxt = p.add(name="berikut"); assert nxt.id == "scene_002"  # id yang dipesan dilepas saat gagal


def test_variations_survive_source_deleted_midway(tmp_path):
    p = Project(tmp_path); a = p.add(GOOD, "Asli")
    made, _ = make_variations(svc(lambda: p.remove(a.id) if p.contains(a.id) else None), p, a.id, 2, auto_check=False)
    assert len(made) == 2 and all(p.contains(m.id) for m in made)


def test_snapshot_of_missing_video_is_a_noop_not_a_crash(tmp_path):
    p = Project(tmp_path); assert p.snapshot("scene_999", "x") is None


def test_project_add_is_thread_safe_unique_ids(tmp_path):
    p = Project(tmp_path)
    def worker():
        for _ in range(40): p.add(name="x")
    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    ids = [i.id for i in p.items]
    assert len(ids) == 320 and len(set(ids)) == 320


def test_concurrent_save_and_mutation_do_not_corrupt(tmp_path):
    p = Project(tmp_path); p.add(name="A")
    stop = threading.Event(); errors = []
    def saver():
        while not stop.is_set():
            try: p.save()
            except Exception as e: errors.append(e)
    t = threading.Thread(target=saver); t.start()
    for n in range(60):
        it = p.add(name=f"v{n}")
        if n % 3 == 0: p.remove(it.id)
    stop.set(); t.join()
    assert errors == []
    q = Project(tmp_path); q.load(); assert len(q.items) >= 1


def test_stress_mixed_operations_from_many_threads(tmp_path):
    """Uji beban: UI (tambah/hapus/simpan/pindah) dan pekerjaan AI (detached → attach) berjalan bersamaan.
    Tidak boleh ada pengecualian, id harus unik, dan berkas proyek konsisten."""
    import random
    p = Project(tmp_path); p.add(name="Awal")
    errors, stop = [], threading.Event()

    def ui_thread(seed):
        rnd = random.Random(seed)
        while not stop.is_set():
            try:
                op = rnd.random()
                if op < .3: p.add(name="ui")
                elif op < .5 and len(p.items) > 1: p.remove(rnd.choice(p.items).id)
                elif op < .7: p.save()
                elif op < .8 and p.items: p.move(rnd.choice(p.items).id, rnd.choice([-1, 1]))
                elif p.items: p.snapshot(rnd.choice(p.items).id, "x")
            except StopIteration:
                pass  # move() pada id yang baru saja dihapus thread lain: kasus sah di UI nyata
            except Exception as e:
                import traceback; errors.append(traceback.format_exc())

    def ai_thread(seed):
        for n in range(40):
            try:
                it = p.detached(GOOD, f"ai{seed}-{n}")
                it.code = GOOD + f"// {n}"
                if (n + seed) % 7 == 0:
                    p.release(it.id); continue   # generasi gagal
                p.attach(it); p.save(); p.history.snapshot(it.id, it.code, "AI generate")
            except Exception as e:
                import traceback; errors.append(traceback.format_exc())

    uis = [threading.Thread(target=ui_thread, args=(i,)) for i in range(3)]
    ais = [threading.Thread(target=ai_thread, args=(i,)) for i in range(3)]
    [t.start() for t in uis + ais]
    [t.join() for t in ais]; stop.set(); [t.join() for t in uis]
    assert errors == [], errors[:3]
    ids = [i.id for i in p.items]
    assert len(ids) == len(set(ids))
    p.save()
    on_disk = {f.stem for f in (tmp_path / "src/compositions").glob("*.tsx")}
    assert on_disk == set(ids)  # file di disk tepat sama dengan daftar (tidak ada yatim / hilang)
    q = Project(tmp_path); q.load(); assert {i.id for i in q.items} == set(ids)


def test_ctx_selected_never_raises_keyerror(tmp_path):
    from vibemotion.config import Settings
    from vibemotion.context import AppContext
    s = Settings(project_dir=str(tmp_path))
    ctx = AppContext(s)
    ctx.project.add(name="B"); ctx.selected_id = "scene_999"
    assert ctx.selected.id == ctx.project.items[0].id and ctx.selected_id == ctx.project.items[0].id
    for it in list(ctx.project.items): ctx.project.remove(it.id)  # proyek kosong (kondisi balapan ekstrem)
    ctx.selected_id = "scene_001"
    assert ctx.selected is not None and len(ctx.project.items) == 1  # dibuatkan satu video kosong


def test_keyerror_message_is_friendly():
    from vibemotion.core.errors import friendly_message
    assert "sudah tidak ada di proyek" in friendly_message("KeyError: 'scene_007'", "id")
    assert "no longer exists" in friendly_message("KeyError: 'scene_007'", "en")
    assert "sudah tidak ada di proyek" in friendly_message(KeyError("scene_007"), "id")  # objek KeyError asli
    assert friendly_message("KeyError: 'bukan_video'", "id").startswith("KeyError")  # KeyError lain tidak disamarkan
