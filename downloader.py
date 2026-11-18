"""Download link final + extract arsip.

Didukung (best-effort):
- MediaFire file page -> cari direct download link di HTML halaman
- Google Drive file -> uc?export=download (dengan confirm token bila perlu)
- Link file langsung (.zip/.7z/.rar/.apk/...) -> download langsung
- Telegram bot (t.me/...) dan halaman lain -> tidak bisa auto-download

Extract: .zip via Python zipfile, .7z/.rar via binary 7z (p7zip-full,
sudah terinstall di Docker image).
"""
import os
import re
import shutil
import subprocess
import zipfile
from urllib.parse import urlparse, parse_qs

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CHUNK = 1024 * 1024  # 1 MB


class DownloadError(Exception):
    pass


def _safe_name(name: str) -> str:
    name = os.path.basename(name.strip()) or "download"
    return re.sub(r"[^A-Za-z0-9._\- ]+", "_", name)


def _filename_from_response(resp, url: str) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    if m:
        return _safe_name(m.group(1))
    path = urlparse(url).path
    name = os.path.basename(path)
    if name and "." in name:
        return _safe_name(name)
    return "download.bin"


def _download_stream(resp, dest_path: str, progress_cb=None) -> str:
    total = int(resp.headers.get("Content-Length") or 0)
    done = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK):
            if not chunk:
                continue
            f.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    return dest_path


def mediafire_direct(url: str, session: requests.Session) -> str:
    """Ambil direct download link dari halaman MediaFire."""
    resp = session.get(url, headers={"User-Agent": UA}, timeout=30)
    if resp.status_code != 200:
        raise DownloadError(f"MediaFire menjawab HTTP {resp.status_code}")
    html = resp.text
    # Tombol download: href="https://downloadXXXX.mediafire.com/..."
    m = re.search(
        r'href="(https://download\d*\.mediafire\.com/[^"]+)"', html
    )
    if not m:
        m = re.search(r"(https://download\d*\.mediafire\.com/[^\s\"'<>]+)", html)
    if not m:
        raise DownloadError(
            "Link download MediaFire tidak ketemu di halaman "
            "(mungkin file dihapus / halaman berubah)."
        )
    return m.group(1)


def drive_direct(url: str, session: requests.Session) -> requests.Response:
    """Return response download Google Drive (handle confirm besar)."""
    file_id = None
    m = re.search(r"/file/d/([^/]+)", url)
    if m:
        file_id = m.group(1)
    else:
        file_id = parse_qs(urlparse(url).query).get("id", [None])[0]
    if not file_id:
        raise DownloadError("ID file Google Drive tidak ketemu.")
    dl = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp = session.get(dl, headers={"User-Agent": UA}, timeout=30,
                       stream=True)
    if "text/html" in resp.headers.get("Content-Type", ""):
        # File besar: Google minta confirm token
        html = resp.text
        m = re.search(r"confirm=([A-Za-z0-9_\-]+)", html)
        if m:
            resp = session.get(
                dl + f"&confirm={m.group(1)}",
                headers={"User-Agent": UA}, timeout=30, stream=True,
            )
        else:
            raise DownloadError(
                "Google Drive minta konfirmasi tambahan (virus scan) "
                "yang tidak bisa dilewati otomatis."
            )
    return resp


def download(url: str, dest_dir: str, progress_cb=None) -> dict:
    """Download link final ke dest_dir. Return {path, filename, size}."""
    os.makedirs(dest_dir, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    host = urlparse(url).netloc.lower()
    if "mediafire.com" in host and "/file/" in url:
        direct = mediafire_direct(url, session)
        resp = session.get(direct, headers={"User-Agent": UA},
                           timeout=60, stream=True)
    elif "drive.google.com" in host:
        resp = drive_direct(url, session)
    elif host.startswith("t.me") or "telegram" in host:
        raise DownloadError(
            "Tujuan adalah bot Telegram — file harus diambil lewat "
            "Telegram (bot), tidak bisa auto-download dari sini."
        )
    else:
        resp = session.get(url, headers={"User-Agent": UA}, timeout=60,
                           stream=True, allow_redirects=True)

    if resp.status_code != 200:
        raise DownloadError(f"Download dijawab HTTP {resp.status_code}")
    ctype = resp.headers.get("Content-Type", "")
    if "text/html" in ctype and "drive.google" not in host:
        raise DownloadError(
            "URL final mengarah ke halaman web, bukan file langsung "
            f"(Content-Type: {ctype}). Download manual dari browser."
        )

    filename = _filename_from_response(resp, resp.url)
    path = os.path.join(dest_dir, filename)
    # Hindari tabrakan nama
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(path):
        path = f"{base}_{i}{ext}"
        i += 1
    _download_stream(resp, path, progress_cb)
    return {
        "path": path,
        "filename": os.path.basename(path),
        "size": os.path.getsize(path),
    }


def extract(path: str, dest_dir: str) -> dict:
    """Extract arsip. Return {extracted_dir, files:[...]}."""
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(path)
    lower = name.lower()

    if lower.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            z.extractall(dest_dir)
            files = z.namelist()
        return {"extracted_dir": dest_dir, "files": files}

    if lower.endswith((".7z", ".rar")):
        seven = shutil.which("7z") or shutil.which("7za")
        if not seven:
            raise DownloadError(
                "Binary 7z tidak ada di container — install p7zip-full."
            )
        r = subprocess.run(
            [seven, "x", "-y", f"-o{dest_dir}", path],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise DownloadError(f"7z gagal: {r.stderr.strip()[:300]}")
        files = []
        for root, _, fnames in os.walk(dest_dir):
            for fn in fnames:
                files.append(os.path.relpath(os.path.join(root, fn), dest_dir))
        return {"extracted_dir": dest_dir, "files": files}

    raise DownloadError(f"Bukan arsip yang bisa di-extract: {name}")
