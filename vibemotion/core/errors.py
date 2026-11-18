"""Ubah error teknis (API, jaringan, Node) menjadi pesan yang bisa ditindaklanjuti."""
from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern, dict[str, str]]] = [
    (re.compile(r"credit balance is too low", re.I), {
        "id": "Saldo kredit API habis. Isi kredit di console.anthropic.com → Plans & Billing, lalu coba lagi.",
        "en": "API credit balance is too low. Add credits at console.anthropic.com → Plans & Billing, then retry."}),
    (re.compile(r"API_KEY_INVALID|api key not valid|invalid x-api-key|invalid api key|incorrect api key|\b401\b", re.I), {
        "id": "API key tidak valid. Periksa key di tab Pengaturan: tempel utuh, tanpa spasi/kutip, di kolom provider yang benar.",
        "en": "API key is not valid. Check the key in Settings: paste it fully, without spaces/quotes, in the right provider field."}),
    (re.compile(r"no longer available|model.*not found|NOT_FOUND|is not supported|does not exist|\b404\b", re.I), {
        "id": "Model tidak tersedia untuk akun/key Anda. Di Pengaturan klik ⟳ Refresh di samping kotak model lalu pilih model dari daftar.",
        "en": "The model is not available for your account/key. In Settings click ⟳ Refresh next to the model box and pick one from the list."}),
    (re.compile(r"\b429\b|quota|RESOURCE_EXHAUSTED|rate.?limit", re.I), {
        "id": "Batas kuota/rate limit tercapai. Tunggu beberapa menit, atau tambah API key lain (satu per baris untuk Gemini).",
        "en": "Quota / rate limit reached. Wait a few minutes, or add another API key (one per line for Gemini)."}),
    (re.compile(r"^\s*5\d\d\b|(?:server|http|gemini|claude|status|error)\W{0,3}5\d\d\b|overloaded|unavailable|server sibuk|tidak tersedia|semua model gemini", re.I), {
        "id": "Server AI sedang sibuk (bukan salah pengaturan Anda). Coba lagi beberapa menit lagi, ganti ke model yang lebih ringan, atau isi Model cadangan / Provider cadangan di Pengaturan.",
        "en": "The AI server is busy (not a problem with your settings). Retry in a few minutes or switch to a lighter model."}),
    (re.compile(r"^KeyError:?\s*'?scene_\d+", re.I), {
        "id": "Video yang dimaksud sudah tidak ada di proyek (mungkin dihapus atau diganti saat proses berjalan). "
              "Coba ulangi; bila berulang, buka Pengaturan → Buka folder log dan kirim isi app.log.",
        "en": "The video no longer exists in the project (it may have been deleted or replaced while a task was running). "
              "Retry; if it repeats, open Settings → Open log folder and send app.log."}),
    (re.compile(r"ReadTimeout|Read timed out|tidak ada jawaban|TimedOut|ConnectTimeout", re.I), {
        "id": "Server tersambung tetapi tidak menjawab tepat waktu. Internet Anda baik-baik saja; modelnya yang lambat atau sedang sibuk. "
              "Coba model yang lebih ringan (mis. flash-lite), isi Model cadangan di Pengaturan, atau ulangi beberapa menit lagi.",
        "en": "The server connected but did not answer in time. Your internet is fine; the model is slow or busy. "
              "Try a lighter model (e.g. flash-lite), set a backup model in Settings, or retry in a few minutes."}),
    (re.compile(r"ConnectionError|Max retries exceeded|getaddrinfo|Name or service not known|timed out|Timeout|"
                r"Failed to establish", re.I), {
        "id": "Tidak bisa terhubung ke internet/server. Periksa koneksi, VPN, atau firewall, lalu coba lagi.",
        "en": "Cannot reach the server. Check your connection, VPN or firewall, then retry."}),
    (re.compile(r"Node\.js tidak ditemukan|npm tidak ditemukan|npx tidak ditemukan", re.I), {
        "id": "Node.js belum terpasang. Pasang LTS dari https://nodejs.org lalu jalankan lagi Setup environment.",
        "en": "Node.js is not installed. Install the LTS from https://nodejs.org then run Setup environment again."}),
    (re.compile(r"npm install gagal|Gagal memasang paket|npm ERR", re.I), {
        "id": "Pemasangan paket npm gagal. Pastikan internet aktif dan coba lagi; lihat detail di log.",
        "en": "npm install failed. Make sure you're online and retry; see the log for details."}),
    (re.compile(r"PermissionError|Access is denied|being used by another process|WinError 32|WinError 5", re.I), {
        "id": "File sedang dipakai program lain atau akses ditolak. Tutup program yang membukanya (mis. Explorer, preview) lalu coba lagi.",
        "en": "The file is in use or access was denied. Close the program using it (e.g. Explorer, preview) and retry."}),
    (re.compile(r"bukan komponen Remotion", re.I), {
        "id": "Balasan AI bukan kode video yang valid. Coba generate ulang, perjelas instruksi, atau ganti model.",
        "en": "The AI reply was not valid video code. Try again, clarify the instructions, or switch model."}),
]


def friendly_message(error: object, lang: str = "id", max_detail: int = 400) -> str:
    """Pesan ramah + detail teknis singkat di bawahnya (untuk laporan)."""
    raw = str(error) if not isinstance(error, BaseException) else f"{type(error).__name__}: {error}"
    raw = raw.strip()
    for pattern, texts in _RULES:
        if pattern.search(raw):
            head = texts.get(lang) or texts["en"]
            label = "Detail" if lang == "en" else "Detail teknis"
            return f"{head}\n\n{label}: {raw[:max_detail]}"
    return raw[: max_detail * 2] or ("Unknown error" if lang == "en" else "Kesalahan tidak diketahui")
