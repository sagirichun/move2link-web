# Move2link Web

Web app self-hosted buat resolve shortlink move2link.co (locker iklan) —
paste link, dapat link final, lalu auto-download + extract arsip.
Satu container Docker, jalan di server sendiri.

## Cara pakai (setelah jalan)

1. Buka `http://IP-server:5000`, login kalau password diaktifkan.
2. Paste salah satu dari:
   - Link shortlink: `https://move2link.co/xxxxxx`
   - URL diary dari log RedirectGuard: `https://diary.siendu.com/...?token=eyJ...&locale=id`
   - Token JWT mentah
3. Klik **Resolve** → keluar link final + tombol **Download & Extract**.
4. File hasil download + hasil extract muncul di daftar "File di server"
   (folder `./downloads`, bisa diunduh balik dari browser).

## Deploy di server (Docker)

```bash
# copy folder ini ke server, lalu:
cd move2link-web
nano docker-compose.yml   # GANTI M2L_PASSWORD + M2L_SECRET dulu!
docker compose up -d --build
# buka http://IP-server:5000
```

Update: `docker compose pull` tidak perlu (image build lokal);
`docker compose up -d --build` lagi setelah edit kode.

## Versi lite (tanpa Chromium, jauh lebih ringan)

Image full bawa Chromium (±1 GB) cuma buat buka shortlink langsung.
Versi lite buang itu semua — inputnya paste URL diary / token JWT
dari log RedirectGuard (jalur yang memang paling andal):

```bash
docker compose -f docker-compose.lite.yml up -d --build
# buka http://IP-server:5000
```

Perbandingan: image full ±1 GB+, lite ±150 MB. Semua fitur lain
(resolve token, download, extract) sama persis.

## Jalan tanpa Docker

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium --with-deps
M2L_PASSWORD=rahasia .venv/bin/python app.py
```

## Yang bisa & yang tidak

| Hal | Status |
|---|---|
| Paste token / URL diary dari RedirectGuard | ✅ jalur andalan, selalu jalan |
| Paste shortlink move2link.co langsung | ⚠️ server coba tangkap token pakai headless Chromium — berhasil kalau Cloudflare lolos di IP server kamu. Kalau gagal, paste token dari HP (RedirectGuard) |
| Link paywall (paywall.move2link.com, bicolink pay link) | ❌ tidak bisa — token baru terbit setelah bayar QRIS |
| Download MediaFire / Google Drive / link file langsung | ✅ best-effort |
| Download tujuan bot Telegram (t.me/...) | ❌ harus lewat Telegram |
| Extract .zip / .7z / .rar | ✅ (.7z/.rar butuh p7zip, sudah di image) |

## Keamanan

- **Jangan expose ke internet publik tanpa password.** Isi `M2L_PASSWORD`
  di `docker-compose.yml` (atau env saat run). Idealnya akses lewat
  Cloudflare Tunnel / Tailscale / VPN rumah saja.
- File yang di-download tersimpan di `./downloads` di server — cek isinya
  sebelum dibuka, sama seperti download dari internet pada umumnya.
- Token move2link sekali pakai: habis di-resolve, token itu hangus.
  Setiap link butuh token fresh dari log RedirectGuard.

## Struktur

```
app.py              Flask app (UI + API + jobs download)
resolver.py         logika resolve: token -> API track/finalize,
                    shortlink -> tangkap token via Playwright
downloader.py       download MediaFire/Drive/direct + extract arsip
templates/          index.html, login.html
downloads/          hasil download + extract (volume Docker)
Dockerfile
docker-compose.yml
requirements.txt
```
