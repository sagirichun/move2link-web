#!/usr/bin/env python3
"""Move2link Web — paste link, dapat link final, auto download + extract.

Jalankan lokal:  python3 app.py   (buka http://localhost:5000)
Docker:          docker compose up -d --build

Env:
  M2L_PASSWORD   (opsional) kalau diisi, halaman login password dulu.
  M2L_PORT       default 5000
  M2L_DOWNLOADS  folder download, default ./downloads
"""
import importlib.util
import os
import threading
import time
import uuid
from functools import wraps

from flask import (Flask, jsonify, render_template, request,
                   send_from_directory, session, redirect, url_for)

from resolver import resolve, ResolveError
from downloader import download, extract, DownloadError

app = Flask(__name__)
app.secret_key = os.environ.get("M2L_SECRET", "m2l-dev-secret-ganti-di-server")
PASSWORD = os.environ.get("M2L_PASSWORD", "")
DOWNLOADS = os.environ.get("M2L_DOWNLOADS",
                           os.path.join(os.path.dirname(__file__), "downloads"))
os.makedirs(DOWNLOADS, exist_ok=True)

jobs = {}  # job_id -> dict(status, ...)
jobs_lock = threading.Lock()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if PASSWORD and not session.get("authed"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "login dulu"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PASSWORD and PASSWORD:
            session["authed"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Password salah.")
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


BROWSER_OK = importlib.util.find_spec("playwright") is not None


@app.route("/")
@login_required
def index():
    return render_template("index.html", browser_ok=BROWSER_OK)


@app.route("/api/resolve", methods=["POST"])
@login_required
def api_resolve():
    data = request.get_json(force=True, silent=True) or {}
    raw = (data.get("input") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "Input kosong."}), 400
    try:
        result = resolve(raw)
    except ResolveError as e:
        return jsonify({"ok": False, "error": str(e)}), 422
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"Error tak terduga: {e}"}), 500
    return jsonify({"ok": True, **result})


def _run_download(job_id: str, url: str):
    job = jobs[job_id]
    try:
        job["status"] = "downloading"
        job["progress"] = (0, 0)

        def cb(done, total):
            job["progress"] = (done, total)

        dl = download(url, DOWNLOADS, progress_cb=cb)
        job["file"] = dl
        job["status"] = "extracting"
        if dl["filename"].lower().endswith((".zip", ".7z", ".rar")):
            out_dir = os.path.join(
                DOWNLOADS,
                os.path.splitext(dl["filename"])[0] + "_extracted",
            )
            ex = extract(dl["path"], out_dir)
            job["extracted"] = ex
            job["status"] = "done"
        else:
            job["status"] = "done"
    except (DownloadError, Exception) as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)


@app.route("/api/download", methods=["POST"])
@login_required
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith("http"):
        return jsonify({"ok": False, "error": "URL tidak valid."}), 400
    job_id = uuid.uuid4().hex[:12]
    with jobs_lock:
        jobs[job_id] = {"id": job_id, "url": url, "status": "queued",
                        "created": time.time()}
    t = threading.Thread(target=_run_download, args=(job_id, url),
                         daemon=True)
    t.start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/jobs")
@login_required
def api_jobs():
    with jobs_lock:
        items = sorted(jobs.values(), key=lambda j: j["created"],
                       reverse=True)[:20]
    out = []
    for j in items:
        d = dict(j)
        if "file" in d:
            d["file"] = {"filename": d["file"]["filename"],
                         "size": d["file"]["size"]}
        out.append(d)
    return jsonify({"ok": True, "jobs": out})


@app.route("/api/files")
@login_required
def api_files():
    items = []
    for root, dirs, files in os.walk(DOWNLOADS):
        dirs.sort()
        for fn in sorted(files):
            p = os.path.join(root, fn)
            items.append({
                "name": os.path.relpath(p, DOWNLOADS),
                "size": os.path.getsize(p),
                "url": "/downloads/" + os.path.relpath(p, DOWNLOADS),
            })
    return jsonify({"ok": True, "files": items})


@app.route("/downloads/<path:fname>")
@login_required
def serve_download(fname):
    return send_from_directory(DOWNLOADS, fname, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("M2L_PORT", "5000"))
    print(f"Move2link Web jalan di http://0.0.0.0:{port}")
    if PASSWORD:
        print("Password login AKTIF (M2L_PASSWORD).")
    else:
        print("PERINGATAN: tanpa password — jangan expose ke internet publik!")
    app.run(host="0.0.0.0", port=port)
