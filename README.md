# Vibe Motion Next

Generator motion graphic berbasis AI untuk **Remotion** — ditulis ulang dari nol, modular, siap dibuild jadi `.exe`.
Dari gambar/instruksi → AI menulis komponen TSX → preview di Remotion Studio → render MP4/WebM/GIF/MOV.

## Fitur
- **Generate**: instruksi + gambar referensi, rasio, FPS, durasi, tema, 8 pilihan gaya, variasi (1–10).
- **Editor**: daftar video (tambah/duplikat/hapus/urut/gabung), edit kode, edit lewat chat AI dengan **Terima/Tolak**, perbaikan otomatis dengan AI, impor aset ke `public/assets`.
- **Preview**: Remotion Studio di proses latar belakang, deteksi error kompilasi + **auto-fix AI** (maks 2 percobaan).
- **Render**: antrean berurutan, progres, batal, format mp4/webm/gif/mov, hardware acceleration, concurrency.
- **AI**: Gemini (multi-key, rotasi otomatis saat 429), **Claude (Anthropic)**, dan provider OpenAI-compatible (OpenAI, OpenRouter, LM Studio…). Tombol ⟳ Refresh di Pengaturan mengambil daftar model terbaru langsung dari API.
- **Ekstensi**: Skills GitHub (`SKILL.md` masuk ke prompt AI) dan Package Manager NPM.
- Dua bahasa (id/en). Setup otomatis Node.js (via winget di Windows) dan `npm install`.

## Menjalankan
```bash
pip install -r requirements.txt
python run.py
```
Butuh Python 3.11+ (dengan Tk) dan Node.js 18+ (diinstal otomatis lewat winget di Windows jika belum ada).

## Build .exe
Di Windows: `build.bat` → `dist\VibeMotionNext.exe`.
Atau lewat GitHub: push repo, jalankan workflow **build-exe** (Actions) dan unduh artifact.

## Struktur
```
run.py                      titik masuk
vibemotion/
  app.py  context.py  config.py  i18n.py
  core/   project.py (model + tulis Root.tsx)  versions.py (versi dipin)  env_setup.py
          preview.py (Studio + pemantau error)  render.py (antrean)  proc.py  code_utils.py  paths.py
  ai/     base.py  gemini.py  openai_compat.py  prompts.py  skills.py  service.py
  ui/     generate_tab.py  editor_tab.py  run_tab.py  settings_tab.py  widgets.py
tests/                      27 tes (pytest)
```

## Keputusan desain
- **Satu file per video** (`src/compositions/scene_NNN.tsx`, ekspor bernama `Remotion`); `Root.tsx` dibuat dari daftar itu.
  Tidak ada `import * as` / `.default`, jadi peringatan webpack "export 'default' was not found" tidak muncul.
- **Versi dipin di `core/versions.py`**: semua `remotion`/`@remotion/*` = 4.0.544 dan `zod` = 4.6.7 (tanpa `^`),
  jadi peringatan "Version mismatch" tidak muncul. Naikkan di satu tempat saat upgrade.
- FFmpeg tidak perlu dipasang terpisah (Remotion 4 membawa sendiri).
- Preview dibuka di browser bawaan (bukan WebView tertanam) agar build ringan dan stabil.
- API key disimpan sebagai teks biasa di `%APPDATA%\VibeMotionNext\config.json` (milik akun Windows Anda).

## Sengaja tidak disertakan dari aplikasi lama
Validasi lisensi, Auto Coder Selenium (otomasi web AI), dan integrasi LAN "MBG PROJECT HQ".

## Stabilitas & diagnostik (v0.7)
- **Log** otomatis di `%APPDATA%\VibeMotionNext\logs\app.log` (berputar, maks ±1.5 MB). Error tak terduga di UI maupun thread latar dicatat di sana dan aplikasi tetap hidup.
- **Pesan error ramah**: kredit habis, API key salah, model tidak tersedia, limit/429, server sibuk (503), tidak ada koneksi, Node.js belum ada, file dipakai program lain — masing-masing dengan langkah perbaikan + detail teknis singkat.
- **Pengaturan → Diagnostik**: tombol *Buka folder log* dan *Salin info diagnostik* (versi, Python, Node, provider/model; API key tidak ikut).
- **Tahan crash**: semua file proyek ditulis atomik; `vibemotion.json` rusak otomatis dipulihkan dari file `.tsx` (salinan lama disimpan sebagai `.corrupt.json`); `config.json` dengan nilai salah tipe tidak membuat aplikasi gagal start.

## Kualitas hasil AI (v0.8)
- **Periksa & perbaiki otomatis** (default aktif): sebelum kode masuk editor dicek — sintaks (esbuild milik proyek), ekspor `Remotion`, paket yang tidak terpasang, aset yang tidak ada, dan pola yang merusak render (`setTimeout`, `Math.random()`, CSS transition). Bila ada masalah, AI memperbaiki sampai 2 kali.
- **Tinjauan visual AI** (opsional, lebih lambat & lebih mahal): render 1 frame tengah, AI menilai (teks terpotong, kontras, kanvas kosong, jauh dari referensi) lalu memperbaiki 1 kali. Perbaikan yang merusak kode ditolak.
- **Storyboard**: satu ide → rencana N adegan (hook → isi → penutup) → tiap adegan digenerate dengan gaya konsisten → opsional digabung jadi satu video.
- **Template bawaan**: Intro judul, Lower third, Hitung mundur, Teks kinetik (ukuran mengikuti rasio apa pun).
- **Transkripsi audio/video → caption** (Editor → 🎙, khusus provider Gemini, maks 18 MB): hasilnya `public/assets/captions_<nama>.json`; minta AI "tambahkan subtitle dari file itu".

## Alur kerja editor (v0.9)
- **Riwayat versi** per video (🕘 / Ctrl+H): snapshot otomatis saat Simpan, hasil AI, sebelum hapus/pulihkan; pratinjau lalu **Pulihkan**. Maks 30 versi per video.
- **Autosave** tiap 15 detik bila ada perubahan (tidak membanjiri riwayat).
- **Syntax highlighting** TS/TSX, **Cari & Ganti** (Ctrl+F; huruf besar/kecil, regex, ganti satu/semua).
- **Thumbnail** di daftar video (tombol 🖼; di-cache, dibuat ulang hanya bila kode/ukuran berubah).
- **Preset ukuran** (YouTube 1080p/4K, TikTok/Reels/Shorts, Instagram, 2:3, sinematik) dan **kualitas draft** render (50%/25%).
- **Ekspor/Impor proyek** (.zip) untuk cadangan atau pindah komputer; impor menambah video baru, tidak menimpa.
- Pintasan: Ctrl+S simpan, Ctrl+F cari, Ctrl+H riwayat.

## Pengujian
```bash
python -m pytest -q                       # 78 tes logika
xvfb-run -a python tools/ui_smoke.py      # tes UI sungguhan dengan AI palsu (Linux; perlu python3-tk)
```

## Distribusi (v0.10)
**Build di Windows** — `build.bat` (atau `python tools/build.py --zip --installer`):
1. menjalankan tes, membuat ikon dan info versi `.exe`;
2. PyInstaller (mode *onedir*: start cepat dan lebih jarang dianggap virus daripada *onefile*) → `dist\VibeMotionNext\VibeMotionNext.exe`;
3. **selftest** pada hasil bungkusan (`VibeMotionNext.exe --selftest`: jendela + semua tab dibuat; gagal = build dibatalkan);
4. zip portabel dan installer Inno Setup (`dist\VibeMotionNext-Setup-<versi>.exe`, per-pengguna, tanpa admin).

**Build otomatis di GitHub** — workflow `build-windows`: jalankan manual (Actions → Run workflow) atau push tag `v0.10` untuk membuat Release berisi installer + zip portabel.

**API key terenkripsi (Windows DPAPI)** — key di `config.json` disimpan sebagai `dpapi:...`, hanya bisa dibuka oleh akun Windows yang sama. Config lama (teks biasa) otomatis dimigrasi saat pertama disimpan. Bila enkripsi gagal, key disimpan apa adanya (tidak pernah hilang). Bila config dibawa ke akun/komputer lain, aplikasi memberi tahu agar key diisi ulang.

**Cek pembaruan** — Pengaturan → Pembaruan: isi URL repo GitHub (`https://github.com/pemilik/repo`, memakai *Release* terbaru) atau URL JSON `{"version": "0.11", "url": "https://...", "notes": "..."}`. Hanya https; tautan non-https dari data eksternal ditolak.

**Peringatan Windows SmartScreen** — `.exe` yang tidak ditandatangani muncul sebagai "penerbit tidak dikenal" (Run anyway / Tetap jalankan). Itu normal untuk aplikasi baru; hilang bila ditandatangani dengan sertifikat code-signing (berbayar), yang bisa ditambahkan di workflow.

## Pemeriksaan di Windows sungguhan (v0.10.1)
Sebagian hal hanya bisa dibuktikan di Windows. Satu skrip menjalankannya dan melaporkan lolos/gagal:
```bat
python tools\check_windows.py                                              :: DPAPI (enkripsi sungguhan) + ikon
python tools\check_windows.py --exe dist\VibeMotionNext\VibeMotionNext.exe  :: properti versi .exe + selftest
python tools\check_windows.py --installer dist\VibeMotionNext-Setup-0.10.exe :: pasang senyap → selftest → uninstall → data AppData selamat
python tools\check_windows.py --repo https://github.com/PEMILIK/REPO        :: cek pembaruan ke GitHub nyata (repo harus punya Release)
```
Opsi boleh digabung. Installer dipasang ke folder sementara dan dihapus kembali; data di `%APPDATA%\VibeMotionNext` tidak disentuh (hanya berkas penanda uji yang dibuat lalu dihapus).

## Ketahanan terhadap error server (v0.11)
- **Model cadangan Gemini** (Pengaturan, pisahkan koma; bawaan `gemini-2.5-flash-lite`): bila model utama tetap sibuk (HTTP 5xx) setelah 5 percobaan ulang, aplikasi otomatis mencoba model cadangan (2 percobaan tiap model). Model cadangan yang tidak tersedia dilewati; model *utama* yang salah (404) tetap dilaporkan, tidak ditutupi.
- **Provider cadangan** (Pengaturan, bawaan `none`): bila provider utama sibuk, kena limit, atau jaringan bermasalah, beralih otomatis ke provider lain yang key-nya terisi (mis. Gemini → Claude). Kesalahan pengaturan seperti API key salah tidak ditutupi.
- Semua kode 5xx (500, 502, 503, 505, 529…) diperlakukan sebagai "server sibuk" dengan pesan yang jelas.

## Kemudahan pakai (v0.12)
- **Tes koneksi** (Pengaturan → 🔌): mengirim permintaan minimal ke provider terpilih dan menjelaskan hasilnya (key salah, model tidak tersedia, kredit habis, server sibuk, tanpa internet). Form disimpan dulu supaya yang diuji = yang terlihat.
- **Panduan awal**: muncul otomatis saat pertama kali bila ada prasyarat belum siap (Node.js, API key, environment Remotion), tiap baris punya tombol aksi; bisa dibuka lagi dari Pengaturan.
- **Pemakaian token & biaya**: dihitung dari angka NYATA yang dikembalikan API (termasuk token "berpikir" Gemini) dan ditampilkan di sidebar. Perkiraan biaya hanya muncul bila Anda mengisi harga per 1 juta token di Pengaturan (harga berubah-ubah, jadi tidak ditebak).
- Label gaya di tab Generate berbahasa Indonesia.

## Kualitas & produktivitas video (v0.13)
- **Varian rasio** (Editor → 📐): salin video ke 9:16, 1:1, 4:5, 2:3, 21:9 sekaligus (nama `Video (9:16)`), dengan opsi *atur ulang layout dengan AI* dan tombol **Buat & render semua**.
- **Audio** (Editor → 🎵): musik latar (di-loop, fade in 1 dtk, fade out di akhir, volume diatur) dan voice-over (volume penuh). Dipasang lewat pembungkus `<Audio>` di `Root.tsx`, jadi kode buatan AI tidak disentuh. Varian rasio ikut membawa audio.
- **Umpan balik cepat** (chip: lebih cepat/lambat, warna lebih cerah, teks lebih besar, lebih sederhana/dramatis) dan **🎲 3 variasi**. Semua edit AI kini juga divalidasi dan diperbaiki otomatis seperti pada Generate.
- **Pustaka pribadi**: *Jadikan template* (muncul di menu template dengan ★) dan **prompt tersimpan**. **8 template bawaan** (+ Kutipan, Statistik, Logo reveal, Grafik batang).
- **Bandingkan dua model**: prompt yang sama dijalankan di model utama dan model pembanding; hasilnya berlabel `· nama-model` berdampingan di daftar.
- Tidak termasuk: voice-over otomatis (TTS) dan durasi otomatis dari panjang audio.

## Distribusi (v0.14)
- **Perbarui sekarang** di dalam aplikasi (versi `.exe`): unduh installer dari Release GitHub, verifikasi SHA-256, pasang senyap. Host, nama berkas, ukuran, pengalihan, dan checksum dibatasi ketat (lihat `RELEASING.md`).
- Workflow GitHub kini **menguji `.exe` dan installer di Windows sungguhan** (pasang senyap → selftest → uninstall → data selamat) sebelum mengunggah hasil.
- `RELEASING.md`: langkah rilis lengkap lewat PowerShell (`gh`), termasuk catatan bahwa repo harus publik untuk pembaruan otomatis.

## CI Windows (v0.14.1)
Build pertama di GitHub Actions menemukan dua masalah yang tidak terlihat di Linux, kini diperbaiki: tes yang membutuhkan PyYAML (tidak ada di `requirements-dev.txt`), dan `tools/check_windows.py` yang akan crash mencetak ✔ ke keluaran bersandi cp1252 (kini UTF-8 paksa di alat dan `PYTHONUTF8=1` di workflow). 206 dari 207 tes sudah lolos di Windows sungguhan pada run pertama.

## v0.14.2
**Cek sekarang** di Pengaturan kini memakai alur yang sama dengan cek otomatis: bila ada versi baru muncul kotak hijau di sidebar (**Perbarui sekarang** pada versi `.exe`, **Unduh** pada versi `python run.py`), dan cek berulang tidak menumpuk kotak.
