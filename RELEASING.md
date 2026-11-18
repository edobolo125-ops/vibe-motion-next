# Merilis Vibe Motion Next (PowerShell)

Build Windows, uji installer di mesin Windows sungguhan, dan Release dikerjakan otomatis oleh GitHub Actions
(workflow `build-windows`). Anda cukup mengunggah kode dan memberi tag.

## 1. Sekali saja: alat
```powershell
winget install -e --id Git.Git
winget install -e --id GitHub.cli
gh auth login          # pilih GitHub.com → HTTPS → login lewat browser
git config --global user.name "Nama Anda"
git config --global user.email "email@anda"
```
Tutup dan buka lagi PowerShell setelah pemasangan.

## 2. Buat repo dan unggah kode
Repo **harus publik** agar pembaruan otomatis di aplikasi bisa membaca dan mengunduh Release tanpa login
(repo privat → aplikasi menganggapnya "belum ada Release"). Repo publik hanya perlu berisi kode ini; API key
Anda tidak pernah ada di sini (disimpan di `%APPDATA%`, terenkripsi).
```powershell
cd C:\jalur\ke\VibeMotionNext
git init -b main
git add .
git commit -m "Vibe Motion Next"
gh repo create vibe-motion-next --public --source . --push
```

## 3. Jalankan build dan uji Windows
```powershell
gh workflow run build-windows --ref main
gh run watch
```
Langkah "Uji pada Windows sungguhan" menjalankan `tools/check_windows.py` pada `.exe` dan installer
(DPAPI, selftest, pasang senyap, uninstall, data pengguna selamat). Job merah = ada yang gagal; lihat lognya:
```powershell
gh run view --log-failed
```
Unduh hasilnya (installer + zip portabel):
```powershell
gh run download --name VibeMotionNext-windows
```

## 4. Rilis resmi
Naikkan `__version__` di `vibemotion/__init__.py`, commit, lalu beri tag:
```powershell
git add .; git commit -m "Rilis 0.15"
git tag v0.15.0
git push origin main --tags
```
Push tag membuat Release di GitHub berisi `VibeMotionNext-Setup-<versi>.exe` dan `...-portable.zip`.

## 5. Hubungkan pembaruan di aplikasi
Pengaturan → Pembaruan → isi `https://github.com/PEMILIK/vibe-motion-next`, centang cek saat dibuka.
Bila ada versi lebih baru: versi `.exe` menampilkan **Perbarui sekarang** (unduh, verifikasi SHA-256 dari
GitHub, pasang senyap, buka lagi aplikasinya dari Start Menu); versi `python run.py` menampilkan **Unduh**
(membuka halaman rilis).

Keamanan unduhan: hanya host GitHub rilis (`github.com`, `objects.githubusercontent.com`,
`release-assets.githubusercontent.com`), nama berkas harus `VibeMotionNext-Setup-*.exe`, ukuran maks 500 MB,
pengalihan ke host lain ditolak, dan checksum yang tidak cocok membuang berkas. Rilis tanpa checksum tetap bisa
dipasang hanya setelah Anda mengonfirmasi.

## Tanda tangan digital (opsional, berbayar)
`.exe` tanpa tanda tangan memunculkan peringatan SmartScreen ("penerbit tidak dikenal"). Untuk
menghilangkannya diperlukan sertifikat code-signing (EV/OV, dari penerbit sertifikat) lalu menandatangani
`dist\VibeMotionNext\VibeMotionNext.exe` dan installer dengan `signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256 ...`
sebelum diunggah. Langkah ini belum ada di workflow karena membutuhkan sertifikat Anda.
