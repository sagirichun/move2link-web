# Dokumentasi Move2link Web

Web app self-hosted untuk resolve shortlink move2link.co (locker iklan):
paste link → dapat link final → auto-download + extract arsip.
Satu container Docker, jalan di server sendiri.

---

## 1. Gambaran umum

| | |
|---|---|
| **Nama** | Move2link Web |
| **Fungsi** | Bypass locker iklan move2link, download & extract file tujuan |
| **Teknologi** | Python 3.12, Flask, Playwright (Chromium headless), requests |
| **Port** | 5000 (bisa diubah lewat `M2L_PORT`) |
| **Data** | File hasil download tersimpan di `./downloads` |

### Alur kerja

```
Paste input ──▶ Resolve ──▶ Link final ──▶ Download & Extract ──▶ File di server
                 │                               │
                 ├─ shortlink move2link.co       ├─ MediaFire (cari direct link)
                 │   → Chromium tangkap token    ├─ Google Drive (uc?export=download)
                 │     dari network request      ├─ Link file langsung
                 ├─ URL diary / token JWT        └─ .zip/.7z/.rar → extract otomatis
                 │   → API track + finalize
                 └─ paywall → DITOLAK (tidak bisa)
```

---

## 2. Kebutuhan sistem

- **Docker (disarankan):** Docker + Docker Compose di server.
  Image berbasis `python:3.12-slim`, sudah termasuk Chromium + p7zip.
- **Tanpa Docker:** Python 3.10+, pip, dan Chromium (via Playwright).
- **Arsitektur:** image bekerja di x86_64 dan arm64 (STB Armbian, Raspberry Pi,
  dsb). Di arm64, instalasi Chromium Playwright lebih lama saat build pertama.
- **RAM:** minimal ±512 MB bebas saat Chromium berjalan.

---

## 3. Instalasi

### 3.1 Docker (disarankan)

```bash
# 1. Copy folder project ke server
tar xzf move2link-web.tar.gz
cd move2link-web

# 2. WAJIB: ganti password & secret di docker-compose.yml
nano docker-compose.yml
#   M2L_PASSWORD=ganti-password-ini   -> isi password login web
#   M2L_SECRET=ganti-secret-acak-ini  -> isi string acak panjang

# 3. Build & jalankan
docker compose up -d --build

# 4. Cek status
docker compose ps
docker compose logs -f m2l

# 5. Buka di browser
#    http://IP-server:5000
```

Update setelah edit kode:

```bash
docker compose up -d --build
```

### 3.1b Versi lite — tanpa Chromium (disarankan untuk STB / server kecil)

Image full membawa Chromium (±1 GB) hanya untuk satu fungsi: membuka
shortlink move2link.co langsung dan menangkap token dari network.
Versi lite membuang Playwright + Chromium sepenuhnya (±150 MB):

```bash
docker compose -f docker-compose.lite.yml up -d --build
# buka http://IP-server:5000
```

Perbedaan dengan versi full:

| | Full | Lite |
|---|---|---|
| Ukuran image | ±1 GB+ | ±150 MB |
| Paste URL diary / token JWT | ✅ | ✅ |
| Paste shortlink move2link.co langsung | ✅ (kalau Cloudflare lolos) | ❌ — halaman web menampilkan petunjuk untuk paste token |
| Download & extract | ✅ | ✅ (sama persis) |

Catatan: jalur token (RedirectGuard) memang jalur yang paling andal —
shortlink langsung di versi full pun tidak dijamin lolos Cloudflare.
Jadi untuk server kecil/STB, **versi lite adalah pilihan yang tepat**.

Berhenti / hapus:

```bash
docker compose down          # stop container (file downloads tetap ada)
docker compose down -v       # stop + hapus volume (hati-hati: downloads ikut terhapus
                             #  kalau memakai volume bernama, bukan bind mount)
```

### 3.2 Tanpa Docker

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium --with-deps
M2L_PASSWORD=rahasia M2L_PORT=5000 .venv/bin/python app.py
# buka http://localhost:5000
```

---

## 4. Konfigurasi

Semua lewat environment variable (di `docker-compose.yml` atau saat run):

| Variable | Default | Keterangan |
|---|---|---|
| `M2L_PASSWORD` | *(kosong)* | Kalau diisi, halaman web minta login password dulu. **Isi sebelum expose ke jaringan.** |
| `M2L_SECRET` | `m2l-dev-secret-ganti-di-server` | Secret session Flask. Ganti dengan string acak. |
| `M2L_PORT` | `5000` | Port web app. |
| `M2L_DOWNLOADS` | `./downloads` | Folder hasil download & extract. Di Docker: `/app/downloads` (bind mount `./downloads`). |

---

## 5. Cara pakai

### 5.1 Resolve link

1. Buka web app, login bila diminta password.
2. Paste salah satu dari tiga bentuk input ini ke kolom besar:
   - **Shortlink:** `https://move2link.co/xxxxxx`
   - **URL diary dari log RedirectGuard:**
     `https://diary.siendu.com/id/blog/...?token=eyJhbGciOi...&locale=id`
   - **Token JWT mentah:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....`
3. Klik **Resolve**.
4. Hasil: slug, PID, **link final**, dan link `go.move2link.co`.
   Tombol **Salin link final** dan **Download & Extract** muncul di kartu hasil.

> **Catatan penting — token sekali pakai.** Token move2link hanya berlaku
> untuk satu kali resolve. Setelah berhasil (atau gagal karena kedaluwarsa),
> token itu hangus. Setiap link butuh token fresh dari log RedirectGuard.

### 5.2 Download & extract

1. Setelah resolve berhasil, klik **Download & Extract**.
2. Job muncul di kartu "Download & Extract" dengan status:
   `queued → downloading → extracting → done` (atau `error` + pesan).
3. File hasil download dan hasil extract muncul di kartu **File di server**,
   bisa diklik untuk diunduh balik ke perangkat kamu.

### 5.3 Jenis tujuan yang didukung

| Tujuan | Auto-download | Keterangan |
|---|---|---|
| MediaFire (`mediafire.com/file/...`) | ✅ | Direct link dicari dari HTML halaman file |
| Google Drive (`drive.google.com/file/d/...`) | ✅ | Lewat `uc?export=download`; file besar kadang minta confirm |
| Link file langsung (`.zip`, `.7z`, `.rar`, `.apk`, dll) | ✅ | Download langsung |
| Bot Telegram (`t.me/...bot`) | ❌ | File harus diambil lewat Telegram |
| Halaman web biasa (bukan file) | ❌ | Pesan error "mengarah ke halaman web" |

### 5.4 Extract arsip

| Format | Cara | Keterangan |
|---|---|---|
| `.zip` | Python `zipfile` | Selalu tersedia |
| `.7z` / `.rar` | Binary `7z` (p7zip-full) | Sudah terinstall di Docker image |
| Format lain | — | Tidak di-extract, tetap tersimpan sebagai file |

Hasil extract masuk ke folder `<nama-file>_extracted` di dalam `downloads`.

---

## 6. API (untuk otomasi / integrasi)

Semua endpoint butuh login dulu bila `M2L_PASSWORD` diaktifkan
(session cookie). Response selalu JSON.

### `POST /api/resolve`

```json
// Request
{ "input": "https://move2link.co/xxxxxx" }

// Response sukses
{ "ok": true, "slug": "xxxxxx", "pid": "2035", "locale": "id",
  "final_url": "https://...", "go_url": "https://go.move2link.co/?to=...&locale=id&pid=2035" }

// Response gagal
{ "ok": false, "error": "Token tidak ketangkap — kemungkinan Cloudflare ..." }
```

### `POST /api/download`

```json
// Request
{ "url": "https://www.mediafire.com/file/.../p1.zip/file" }

// Response
{ "ok": true, "job_id": "0bdfdb8e73cb" }
```

### `GET /api/jobs`

Daftar 20 job terakhir (status, progress, file, error).

### `GET /api/files`

Daftar semua file di folder downloads beserta link download-nya.

### `GET /downloads/<nama-file>`

Download file dari server ke browser.

---

## 7. Struktur file

```
move2link-web/
├── app.py              Flask app: UI, API, job download (thread), login
├── resolver.py         Resolve: parse token/URL, API track + finalize,
│                       tangkap token shortlink via Playwright
├── downloader.py       Download MediaFire/Drive/direct + extract arsip
├── templates/
│   ├── index.html      Halaman utama (paste, hasil, jobs, file)
│   └── login.html      Halaman login password
├── downloads/          Hasil download + extract (volume Docker)
├── requirements.txt    flask, requests, playwright
├── Dockerfile          python:3.12-slim + Chromium + p7zip-full
├── docker-compose.yml  Service m2l, port 5000, volume downloads
├── .dockerignore
├── README.md           Ringkasan singkat
└── DOKUMENTASI.md      Dokumen ini
```

---

## 8. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| **"Token tidak ketangkap — kemungkinan Cloudflare memblokir browser server"** | IP server kamu di-flag Cloudflare. Solusi: paste token dari log RedirectGuard di HP (jalur yang selalu jalan). Coba juga restart container — kadang IP/session baru lolos. |
| **"API dijawab HTTP 400 — token sudah terpakai/kedaluwarsa"** | Token sekali pakai dan sudah habis, atau kedaluwarsa (±5 hari dari dibuat). Ambil token fresh: buka shortlink di HP, lewati captcha, copy URL diary dari log RedirectGuard. |
| **"Link ini PAYWALL (bayar QRIS dulu...)"** | Link tersebut memang berbayar (mis. `paywall.move2link.com` atau bicolink pay link). Token tidak diterbitkan sebelum bayar — tidak bisa diproses script ini. Bayar manual via QRIS dari HP, atau minta link locker biasa. |
| **"Link download MediaFire tidak ketemu"** | File dihapus dari MediaFire atau struktur halaman berubah. Coba buka link MediaFire-nya manual di browser untuk memastikan file masih ada. |
| **"Tujuan adalah bot Telegram"** | Tujuan akhirnya bot Telegram — file harus diambil lewat bot di aplikasi Telegram, tidak bisa auto-download. |
| **"Google Drive minta konfirmasi tambahan"** | File besar + Google minta scan virus. Download manual dari browser. |
| **"Binary 7z tidak ada"** | Terjadi kalau jalan tanpa Docker dan p7zip belum terinstall. Install: `sudo apt install p7zip-full`. |
| **Port 5000 sudah dipakai** | Ubah mapping port di `docker-compose.yml` (mis. `"5001:5000"`) lalu `docker compose up -d`. |
| **Halaman tidak bisa dibuka sama sekali** | Cek `docker compose ps` dan `docker compose logs -f m2l`. Pastikan firewall server mengizinkan port 5000, atau akses via `http://localhost:5000` dari dalam server. |
| **Build Docker lama / gagal di STB arm64** | Build pertama mengunduh Chromium (±150 MB). Pastikan koneksi stabil dan ruang disk cukup (±1 GB). Ulangi `docker compose up -d --build` bila terputus di tengah jalan. |

---

## 9. Keamanan

- **Jangan expose ke internet publik tanpa password.** Isi `M2L_PASSWORD`
  sebelum menjalankan. Idealnya akses hanya lewat jaringan rumah,
  Cloudflare Tunnel, Tailscale, atau VPN.
- Tool ini mengunduh file dari internet ke server kamu — cek isi file
  sebelum dibuka/dijalankan, seperti download biasa.
- Token dan link yang kamu paste hanya dipakai untuk satu kali resolve
  dan tidak disimpan ke database (hanya log job di memori).
- Jangan jalankan file hasil extract yang tidak kamu kenali (terutama
  `.exe`, `.apk`, script) tanpa memeriksa dulu.

---

## 10. Batasan yang diketahui

1. **Shortlink otomatis tergantung Cloudflare.** Server harus lolos
   Cloudflare dengan headless Chromium. Ini tidak bisa dijamin dari semua
   IP — fallback resmi: paste token dari RedirectGuard.
2. **Token sekali pakai & berumur pendek** (±5 hari, hangus setelah finalize).
3. **Paywall tidak bisa dilewati** (by design — token baru ada setelah bayar).
4. **Tidak ada antrian multi-user / database.** Job tersimpan di memori;
   restart container menghapus riwayat job (file downloads tetap ada).
5. **MediaFire & Google Drive bersifat best-effort** — kalau struktur
   halaman mereka berubah, resolver perlu diperbarui.
