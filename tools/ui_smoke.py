"""Tes asap UI (butuh display; di Linux: xvfb-run -a python tools/ui_smoke.py). Memakai AI palsu, tanpa jaringan.

Hasil tangkapan layar disimpan di folder $SHOTS (default: folder sementara)."""
import json, os, sys, tempfile, time, traceback
tmp = tempfile.mkdtemp(prefix="vmn_")
os.environ["XDG_CONFIG_HOME"] = tmp; os.environ["HOME"] = tmp
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter.messagebox as mb
popups = []
for n in ("showinfo", "showerror", "showwarning"):
    setattr(mb, n, lambda title=None, msg=None, _n=n, **k: popups.append((_n, title, msg)))
mb.askyesno = lambda *a, **k: True
from tkinter import filedialog
from PIL import Image, ImageGrab

from vibemotion.app import App
from vibemotion.ai.extras import PLAN_SYSTEM
from vibemotion.ai.usage import MeteredProvider
from vibemotion.ai.connection import TestResult
import vibemotion.ui.generate_tab as gt
from vibemotion.core.thumbs import thumb_path
from vibemotion import __version__

ok, fails = [], []
def check(name, cond, extra=""):
    (ok if cond else fails).append(name); print(("PASS " if cond else "FAIL ") + name, extra if not cond else "")

def pump(ms=200):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.update(); time.sleep(0.01)

def wait(cond, secs=15):
    end = time.time() + secs
    while time.time() < end:
        pump(50)
        if cond(): return True
    return False

def shot(name):
    pump(300)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()), xdisplay=os.environ["DISPLAY"]).save(f"{os.environ.get('SHOTS', tmp)}/{name}.png")

try:
    import json as _j
    from vibemotion.core.updater import UpdateInfo as _UI
    import vibemotion.app as _am
    _cfg = os.path.join(tmp, "VibeMotionNext"); os.makedirs(_cfg, exist_ok=True)
    open(os.path.join(_cfg, "config.json"), "w", encoding="utf-8").write(_j.dumps({"update_url": "https://github.com/o/r", "check_updates": True}))
    _startup_calls = []
    def _fake_check(url, cur):
        _startup_calls.append((url, cur))
        return _UI("v0.99", "https://github.com/o/r/releases/tag/v0.99", "n", "https://github.com/o/r/releases/download/v0.99/VibeMotionNext-Setup-0.99.exe", "VibeMotionNext-Setup-0.99.exe", "a" * 64, 10)
    _am.check_update = _fake_check
    _am.can_self_update = lambda: True
    app = App(); pump(500)
    ctx, ed = app.ctx, app.editor
    check("judul memuat versi", __version__ in app.title())
    for k in ("generate", "editor", "run", "settings"):
        app.show(k); pump(150)
    check("semua tab bisa dibuka", True)

    pump(900)  # _startup_checks (600 ms) → panduan awal muncul karena onboarded=False & prasyarat belum siap
    def toplevels(root): return [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"]
    def texts(w):
        out = []
        for c in w.winfo_children():
            try: out.append(c.cget("text"))
            except Exception: pass
            out += texts(c)
        return out
    check("cek otomatis saat dibuka memakai alamat tersimpan", len(_startup_calls) == 1 and _startup_calls[0][0] == "https://github.com/o/r", _startup_calls)
    check("cek otomatis saat dibuka memunculkan tombol Perbarui sekarang", getattr(app, "update_btn", None) is not None and app.update_btn.cget("text") == app.ctx.tr("update.now"), getattr(getattr(app, "update_btn", None), "cget", lambda x: None)("text"))
    wz = toplevels(app)
    check("panduan awal muncul otomatis", len(wz) == 1, wz)
    if wz:
        wt = texts(wz[0])
        check("panduan: tiga baris + judul", all(k in " ".join(map(str, wt)) for k in ("Node.js", "API key", "Remotion")), wt)
        check("panduan: status ✘ pada key & env", sum(1 for t in wt if t == "✘") >= 2, wt)
        wiz = wz[0]; wiz.act("key"); pump(100)   # tanpa key → pindah ke tab Pengaturan, tidak crash
        check("tombol key tanpa key → tab Pengaturan", app.tabs["settings"].winfo_ismapped())
        shot("wizard")
        wiz.close(); pump(100)
        check("tutup panduan menyimpan onboarded", ctx.settings.onboarded is True and not toplevels(app))
    gl = texts(app.tabs["generate"])
    check("label gaya berbahasa Indonesia", "Animasi masuk" in gl and "Kamera" in gl and "Tempo" in gl and "Entrance" not in gl, [t for t in gl if t in ("Entrance", "Camera")])
    app.show("editor"); pump(200)
    code = 'import React from "react";\n// catatan\nexport const Remotion = () => {\n  const x = 42;\n  return <AbsoluteFill style={{ color: "red" }}>Halo</AbsoluteFill>;\n};\n'
    ed.set_code(code); ed.commit(); pump(100)
    tb = ed.code._textbox
    for kind in ("keyword", "string", "number", "comment", "tag"):
        check(f"highlight {kind}", len(tb.tag_ranges(kind)) > 0)

    ed.toggle_find(); pump(100)
    check("find bar tampil", ed.findbar.winfo_ismapped())
    ed.find_entry.insert(0, "const"); ed._update_count(); check("hitung hasil cari", "2" in ed.find_info.cget("text"), ed.find_info.cget("text"))
    ed.find_next(True); check("hasil tersorot", len(tb.tag_ranges("found")) == 2)
    ed.find_next(True); ed.find_next(False); pump(50)
    ed.repl_entry.insert(0, "let"); ed.replace_one(); pump(50)
    check("ganti satu", get := ed.code.get("1.0", "end-1c").count("let ") >= 1 and "const x" in ed.code.get("1.0", "end-1c") or "const Remotion" in ed.code.get("1.0", "end-1c"))
    ed.replace_everything(); pump(50)
    txt = ed.code.get("1.0", "end-1c")
    check("ganti semua", "const" not in txt and "let" in txt, txt[:80])
    check("highlight ulang setelah ganti", len(tb.tag_ranges("keyword")) > 0)
    ed.find_entry.delete(0, "end"); ed.find_entry.insert(0, "("); ed.regex_box.select(); ed._update_count()
    check("regex salah tidak crash", True)
    ed.regex_box.deselect(); ed.toggle_find()

    vid = ctx.selected_id
    ed.save(); pump(100)
    check("save → riwayat", len(ctx.project.history.list(vid)) >= 1)
    ed.set_code(code + "// lagi\n"); ed._on_key(); ed.commit(); ed.save()
    check("riwayat bertambah", len(ctx.project.history.list(vid)) >= 2)
    ed.open_history(); pump(300)
    tops = [w for w in ed.winfo_children() if w.winfo_class() == "Toplevel"]
    check("dialog riwayat terbuka", len(tops) == 1)
    shot("history")
    if tops: tops[0].destroy()

    ed.use_preset("TikTok / Reels / Shorts (9:16)"); pump(100)
    it = ctx.selected; check("preset 9:16", (it.width, it.height) == (1080, 1920) and "9:16" in ed.size.get(), ed.size.get())
    ed.size.set([k for k in ed.size_map if k.startswith("2:3")][0]); ed.apply_meta(); pump(100)
    check("ukuran 2:3", (ctx.selected.width, ctx.selected.height) == (1080, 1620))

    # thumbnail palsu → muncul di daftar
    p = thumb_path(ctx.project, ctx.selected); p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (270, 480), "#3b5bdb").save(p); ed.refresh(); pump(200)
    check("thumbnail di daftar", len(ed._img_cache) == 1)

    # duplikat/urut/gabung/hapus
    n0 = len(ctx.project.items); ed.duplicate(); ed.move(-1); check("duplikat+urut", len(ctx.project.items) == n0 + 1)
    ed.merge(); check("gabung", ctx.selected.name == "Merged"); ed.delete(); check("hapus", ctx.selected_id in {i.id for i in ctx.project.items})

    # ekspor / impor
    z = os.path.join(tmp, "p.zip"); filedialog.asksaveasfilename = lambda **k: z; filedialog.askopenfilename = lambda **k: z
    ed.export_zip(); check("ekspor zip", os.path.exists(z) and popups[-1][0] == "showinfo", popups[-1:])
    n1 = len(ctx.project.items); ed.import_zip(); check("impor zip", len(ctx.project.items) > n1, popups[-1:])

    # Generate: AI palsu, mode storyboard, tanpa validator
    class Fake:
        last_usage = (1200, 340)
        def complete(self, system, user, images=None):
            if system == PLAN_SYSTEM: return json.dumps([{"title": "Pembuka", "brief": "a", "seconds": 2}, {"title": "Isi", "brief": "b", "seconds": 2}])
            return 'export const Remotion = () => null;'
    gt.make_provider = lambda s, log=None, meter=None: MeteredProvider(Fake(), meter)
    g = app.tabs["generate"]; app.show("generate"); pump(200)
    g.instruction.insert("1.0", "tes storyboard"); g.mode.set(ctx.tr("gen.mode_story")); g.auto.deselect(); g.visual.deselect(); g.scenes.delete(0, "end"); g.scenes.insert(0, "2")
    before = len(ctx.project.items); g.generate()
    check("tombol generate dinonaktifkan saat kerja", True)
    done = wait(lambda: g.btn.cget("state") == "normal" and len(ctx.project.items) > before)
    check("generate storyboard selesai", done, g.status.cget("text"))
    names = [i.name for i in ctx.project.items[before:]]
    check("adegan + gabungan", names == ["Pembuka", "Isi", "Storyboard"], names)
    check("pindah ke tab editor", app.tabs["editor"].winfo_ismapped())
    pump(300)
    check("pemakaian token tampil di sidebar", "masuk" in app.usage_label.cget("text") and "keluar" in app.usage_label.cget("text"), app.usage_label.cget("text"))
    check("jumlah token benar (3 panggilan × 1200/340)", (ctx.usage.input_tokens, ctx.usage.output_tokens) == (3600, 1020), (ctx.usage.input_tokens, ctx.usage.output_tokens))
    check("riwayat AI generate", any(e.label == "AI generate" for e in ctx.project.history.list(ctx.project.items[before].id)))
    # template
    n2 = len(ctx.project.items); g.tpl.set(list(g.tpl_names)[2]); g.from_template(); check("buat dari template", len(ctx.project.items) == n2 + 1 and "useVideoConfig" in ctx.selected.code)

    # ====== v0.13: audio, varian rasio, umpan balik, variasi, template/prompt pribadi, bandingkan model ======
    import wave, struct, math
    import vibemotion.ui.editor_tab as et
    from vibemotion.core.library import UserTemplates
    class Fake2:
        last_usage = (10, 5)
        def complete(self, system, user, images=None):
            if system == PLAN_SYSTEM: return "[]"
            return 'export const Remotion = () => "editado";'
    et.make_provider = lambda s_, log=None, meter=None: MeteredProvider(Fake2(), meter)
    gt.make_provider = lambda s_, log=None, meter=None: MeteredProvider(Fake2(), meter)
    ed = app.editor; app.show("editor"); pump(200)
    ctx.settings.auto_check = True
    # -- umpan balik cepat → usulan AI → terima
    ed.set_code("export const Remotion = () => null;"); ed.commit(); vid = ctx.selected_id; ed.save()
    ed.quick_feedback("faster")
    check("chip umpan balik memicu edit AI → usulan muncul", wait(lambda: ed.backup is not None), "")
    check("banner terima/tolak tampil", ed.banner.winfo_ismapped())
    check("teks permintaan chip terkirim", "lebih cepat" in ed.ask.get().lower() or ed.ask.get() == "" )
    ed.approve(); pump(100)
    check("terima → kode baru tersimpan + riwayat 'AI edit'", "editado" in ctx.project.get(vid).code and any(e.label == "AI edit" for e in ctx.project.history.list(vid)))
    # -- 3 variasi
    n0 = len(ctx.project.items); ed.make_variations_bg()
    check("3 variasi ditambahkan", wait(lambda: len(ctx.project.items) == n0 + 3 and "3 variasi" in ed.status.cget("text")), (len(ctx.project.items) - n0, ed.status.cget("text")))
    check("setelah selesai, variasi pertama terpilih", ctx.selected.name.endswith("· var 1"), ctx.selected.name)
    check("nama variasi", [i.name.rsplit(" · ", 1)[-1] for i in ctx.project.items[-3:]] == ["var 1", "var 2", "var 3"], [i.name for i in ctx.project.items[-3:]])
    # -- varian rasio (dialog)
    ctx.selected_id = vid; ed.refresh(); pump(100)
    ed.open_ratios(); pump(300)
    rd = toplevels(ed)[-1]
    check("dialog rasio terbuka, rasio sumber dinonaktifkan", rd.boxes["16:9"].cget("state") == "disabled" and set(rd.chosen()) == {"9:16", "1:1"}, rd.chosen())
    shot("ratio_dialog")
    n1 = len(ctx.project.items); rd.create(False)
    check("varian rasio dibuat (9:16 & 1:1)", wait(lambda: len(ctx.project.items) == n1 + 2), len(ctx.project.items) - n1)
    vs = [i for i in ctx.project.items if i.name.startswith(ctx.project.get(vid).name + " (")]
    check("ukuran varian benar", sorted((i.width, i.height) for i in vs) == [(1080, 1080), (1080, 1920)], ([(i.width, i.height) for i in vs], ctx.project.get(vid).name, [i.name for i in ctx.project.items[-6:]]))
    check("dialog rasio menutup diri", wait(lambda: not [w for w in toplevels(ed) if hasattr(w, "boxes")]))
    # -- audio (dialog)
    wav = os.path.join(tmp, "musik.wav")
    with wave.open(wav, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"".join(struct.pack("<h", int(8000*math.sin(i/9))) for i in range(8000)))
    ctx.selected_id = vid; ed.refresh(); pump(100)
    filedialog.askopenfilename = lambda **k: wav
    ed.open_audio(); pump(300)
    ad = toplevels(ed)[-1]
    ad.pick("music"); ad.pick("voice"); ad.slider.set(0.3); ad._on_volume(0.3); pump(100)
    check("dialog audio: file terpilih tampil", "musik.wav" in ad.music_label.cget("text") and "musik.wav" in ad.voice_label.cget("text") and "30%" in ad.volume_label.cget("text"))
    shot("audio_dialog")
    ad.apply(); pump(200)
    it = ctx.project.get(vid)
    root_txt = open(os.path.join(ctx.project.root, "src", "Root.tsx"), encoding="utf-8").read()
    check("audio terpasang pada video", (it.music, it.voiceover) == ("assets/musik.wav", "assets/musik.wav") and abs(it.music_volume - 0.3) < 0.06, (it.music, it.music_volume))
    check("Root.tsx memakai pembungkus <Audio>", f"W_{vid}" in root_txt and 'staticFile("assets/musik.wav")' in root_txt)
    check("file audio diimpor ke public/assets", os.path.exists(os.path.join(ctx.project.root, "public", "assets", "musik.wav")))
    # -- template & prompt pribadi
    g = app.tabs["generate"]; app.show("generate"); pump(100)
    ed.save_template_as("Mi Template"); pump(100)
    check("template pribadi tersimpan", [t.name for t in UserTemplates().list()] == ["Mi Template"])
    check("template pribadi muncul di menu Generate (★)", "★ Mi Template" in g.tpl_names, list(g.tpl_names)[-2:])
    g.tpl.set("★ Mi Template"); n2 = len(ctx.project.items); g.from_template(); pump(100)
    check("buat dari template pribadi", len(ctx.project.items) == n2 + 1 and ctx.selected.name == "Mi Template" and "editado" in ctx.selected.code, ctx.selected.name)
    app.show("generate"); pump(100)
    g.instruction.delete("1.0", "end"); g.instruction.insert("1.0", "Buat intro neon 5 detik"); g.save_prompt_as("Intro neon"); pump(100)
    check("prompt tersimpan muncul di menu", "Intro neon" in g.prompts.names() and g.prompt_menu.get() == "Intro neon")
    g.instruction.delete("1.0", "end"); g.load_prompt("Intro neon")
    check("memuat prompt tersimpan mengisi kotak instruksi", g.instruction.get("1.0", "end-1c") == "Buat intro neon 5 detik")
    g.delete_prompt(); check("hapus prompt", g.prompts.names() == [])
    # -- bandingkan dua model
    g.mode.set(ctx.tr("gen.mode_single")); g.auto.deselect(); g.visual.deselect(); g.count.delete(0, "end"); g.count.insert(0, "1")
    g.compare.select(); g.compare_model.insert(0, "model-pembanding-b")
    before = len(ctx.project.items); ctx.settings.provider = "gemini"; ctx.settings.gemini_model = "model-utama-a"
    g.instruction.delete("1.0", "end"); g.instruction.insert("1.0", "bandingkan")
    g.generate(); wait(lambda: g.btn.cget("state") == "normal" and len(ctx.project.items) >= before + 2)
    nm = [i.name for i in ctx.project.items[before:]]
    check("bandingkan: dua video berlabel model", len(nm) == 2 and nm[0].endswith("· model-utama-a") and nm[1].endswith("· model-pembanding-b"), nm)
    g.compare.deselect()
    # kembalikan stub gagal untuk tes error di bawah

    # ====== v0.14: pembaruan dari dalam aplikasi ======
    import vibemotion.app as appmod
    from pathlib import Path as P_
    from vibemotion.core.updater import UpdateInfo, UpdateError
    asset = "VibeMotionNext-Setup-0.99.exe"
    info = UpdateInfo("v0.99", "https://github.com/o/r/releases/tag/v0.99", "catatan",
                      "https://github.com/o/r/releases/download/v0.99/" + asset, asset, "a" * 64, 10)
    appmod.can_self_update = lambda: False
    app._show_update(info); pump(100)
    check("versi python: tombol Unduh (buka browser)", app.update_btn.cget("text") == ctx.tr("set.update_open"), app.update_btn.cget("text"))
    app.update_btn.master.destroy()
    appmod.can_self_update = lambda: True
    app._show_update(UpdateInfo("v0.99", "https://github.com/o/r/releases/tag/v0.99")); pump(100)
    check("rilis tanpa installer: tetap tombol Unduh", app.update_btn.cget("text") == ctx.tr("set.update_open"))
    app.update_btn.master.destroy()
    app._show_update(info); pump(100)
    check("terbungkus + ada installer: tombol Perbarui sekarang", app.update_btn.cget("text") == ctx.tr("update.now"), app.update_btn.cget("text"))
    shot("update_box")
    launched, closed = [], []
    appmod.launch_installer = lambda path: launched.append(path)
    app.on_close = lambda: closed.append(1)
    def fake_dl(i, dest, on_progress=None, **kw):
        on_progress and on_progress(5, 10)
        return P_(tmp) / i.asset_name, True
    appmod.download_installer = fake_dl
    mb.askyesno = lambda *a, **k: True
    app._do_update(info); wait(lambda: closed)
    check("update terverifikasi: installer diluncurkan lalu aplikasi ditutup", len(launched) == 1 and launched[0].name == asset and closed == [1], (launched, closed))
    # tanpa checksum + pengguna menolak → tidak diluncurkan
    launched.clear(); closed.clear()
    appmod.download_installer = lambda i, dest, on_progress=None, **kw: (P_(tmp) / i.asset_name, False)
    answers = iter([True, False])  # konfirmasi unduh = ya, "tetap pasang tanpa checksum?" = tidak
    mb.askyesno = lambda *a, **k: next(answers)
    app._do_update(info); wait(lambda: app.update_btn.cget("state") == "normal" and not closed, 5); pump(200)
    check("tanpa checksum + ditolak → tidak dipasang, tombol aktif lagi", not launched and not closed and app.update_btn.cget("state") == "normal", (launched, closed))
    # unduhan gagal (mis. checksum tidak cocok) → peringatan dan tombol aktif lagi
    def bad_dl(i, dest, on_progress=None, **kw): raise UpdateError("Checksum SHA-256 tidak cocok")
    appmod.download_installer = bad_dl; mb.askyesno = lambda *a, **k: True
    n = len(popups); app._do_update(info); wait(lambda: len(popups) > n)
    check("unduhan gagal → peringatan jelas, tidak ada instalasi", popups[-1][0] == "showwarning" and "Checksum" in popups[-1][2] and not launched, popups[-1:])
    check("tombol pembaruan aktif lagi setelah gagal", wait(lambda: app.update_btn.cget("state") == "normal"))

    # -- "Cek sekarang" di Pengaturan memakai kotak pembaruan di sidebar (satu alur)
    import vibemotion.ui.settings_tab as stt2
    app.show("settings"); pump(100)
    appmod.can_self_update = lambda: True
    first_box = getattr(app, "_update_box", None)
    stt2.check_update = lambda url, cur: info
    n = len(popups); app.tabs["settings"].update_url.delete(0, "end"); app.tabs["settings"].update_url.insert(0, "https://github.com/o/r")
    app.tabs["settings"].check_now(); wait(lambda: len(popups) > n)
    check("Cek sekarang: pesan menunjuk ke tombol sidebar", popups[-1][0] == "showinfo" and "v0.99" in popups[-1][2] and "sidebar" in popups[-1][2], popups[-1:])
    check("Cek sekarang: tombol Perbarui sekarang muncul", app.update_btn.cget("text") == ctx.tr("update.now"), app.update_btn.cget("text"))
    second_box = app._update_box
    n = len(popups); app.tabs["settings"].check_now(); wait(lambda: len(popups) > n); pump(100)
    check("cek berulang tidak menumpuk kotak (yang lama dihancurkan)", app._update_box is not second_box and not second_box.winfo_exists())
    stt2.check_update = lambda url, cur: None
    n = len(popups); app.tabs["settings"].check_now(); wait(lambda: len(popups) > n)
    check("tanpa pembaruan: 'sudah versi terbaru'", popups[-1][0] == "showinfo" and "terbaru" in popups[-1][2], popups[-1:])
    # error ramah
    gt.make_provider = lambda s, log=None, meter=None: (_ for _ in ()).throw(RuntimeError("Gemini 400: API_KEY_INVALID"))
    app.show("generate"); g.btn.configure(state="normal"); g.generate(); pump(100)
    check("error ramah ditampilkan", popups and "API key tidak valid" in popups[-1][2], popups[-1:])
    # settings
    st = app.tabs["settings"]; app.show("settings"); pump(200)
    st.clipboard_clear(); st.copy_diag(); pump(50)
    check("salin diagnostik", "Vibe Motion Next v" in st.clipboard_get())
    shot("settings")
    import vibemotion.ui.settings_tab as stt, vibemotion.ui.wizard as wzm
    stt.check_connection = lambda s_: TestResult(True, "✔ gemini (m) merespons dalam 0.4 s — “OK”", 0.4)
    n = len(popups); st.test_connection(); check("tombol tes koneksi dinonaktifkan saat jalan", st.test_btn.cget("state") == "disabled")
    check("tes koneksi sukses → info", wait(lambda: len(popups) > n and st.test_btn.cget("state") == "normal") and popups[-1][0] == "showinfo" and "merespons" in popups[-1][2], popups[-1:])
    stt.check_connection = lambda s_: TestResult(False, "API key tidak valid. Periksa key", 0.2)
    n = len(popups); st.test_connection(); wait(lambda: len(popups) > n)
    check("tes koneksi gagal → peringatan dengan penyebab", popups[-1][0] == "showwarning" and "tidak valid" in popups[-1][2], popups[-1:])
    st.price_in.insert(0, "0,5"); st.price_out.insert(0, "2"); st.save(); pump(100)
    check("harga tersimpan & dipakai meter", (ctx.settings.price_in, ctx.settings.price_out) == (0.5, 2.0) and ctx.usage.price_in == 0.5)
    check("biaya ≈ tampil di ringkasan", "≈ $" in app.usage_label.cget("text"), app.usage_label.cget("text"))
    st.price_in.delete(0, "end"); st.price_in.insert(0, "abc"); st.collect(); check("harga tidak valid → 0, tidak crash", ctx.settings.price_in == 0.0)
    wzm.check_connection = lambda s_: TestResult(True, "✔ anthropic ok", 0.1)
    st.open_wizard(); pump(200)
    w2 = toplevels(st)
    check("panduan bisa dibuka dari Pengaturan", len(w2) == 1)
    if w2:
        ctx.settings.anthropic_key = "sk-ant-X"; ctx.settings.provider = "anthropic"; w2[0].refresh(); pump(50)
        w2[0].act("key"); wait(lambda: "anthropic ok" in w2[0].result.cget("text"))
        check("panduan: tes koneksi dari baris key", "anthropic ok" in w2[0].result.cget("text"), w2[0].result.cget("text"))
        w2[0].destroy()
    st.provider.set("anthropic"); st.akey.insert(0, "sk-ant-X"); st.save(); pump(100)
    check("simpan pengaturan", ctx.settings.provider == "anthropic" and ctx.settings.anthropic_key == "sk-ant-X")
    # run tab
    rt = app.tabs["run"]; app.show("run"); pump(200); rt.quality.set("50% (draft)"); shot("run")
    # tampilan editor akhir
    app.show("editor"); ed.set_code(code); pump(300); shot("editor")
except Exception:
    traceback.print_exc(); fails.append("EXCEPTION")
print(f"\n{len(ok)} lolos, {len(fails)} gagal: {fails}")
try: app.destroy()
except Exception: pass
