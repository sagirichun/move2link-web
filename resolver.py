"""Resolver move2link locker iklan.

Dua jalur masuk:
1. Token/URL diary (jalur andalan) — user paste URL diary.siendu.com
   dari log RedirectGuard, atau token JWT-nya langsung.
2. Shortlink move2link.co (jalur otomatis) — server buka link pakai
   headless Chromium, tangkap token dari NETWORK REQUEST sebelum JS
   halaman sempat menghapusnya dari address bar, lalu lanjut jalur 1.
   Jalur ini butuh browser lolos Cloudflare; kalau gagal, fallback ke
   jalur 1 dengan pesan yang jelas.

Link PAYWALL (paywall.move2link.com / bicolink pay link) TIDAK bisa
diproses — tokennya memang tidak diterbitkan sebelum bayar.
"""
import base64
import json
import re
import urllib.parse
import urllib.request
import urllib.error
import http.client
import time

API = "https://m2l-api.siendu.com/api/v1"
CSRF_TOKEN = "f62i45iojk53j53kjqnfa"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SHORTLINK_RE = re.compile(r"^https?://(?:www\.)?move2link\.co/([A-Za-z0-9]+)/?$")


class ResolveError(Exception):
    pass


def b64d(s: str) -> str:
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode()


def parse_input(raw: str):
    """URL diary / token mentah -> (token, locale|None)."""
    raw = raw.strip().strip('"').strip("'")
    if "token=" in raw:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        if "token" not in qs:
            raise ResolveError("URL tidak mengandung ?token=.")
        return qs["token"][0], qs.get("locale", [None])[0]
    if raw.startswith("eyJ") and raw.count(".") == 2:
        return raw, None
    raise ResolveError(
        "Input tidak dikenali. Paste URL diary.siendu.com yang ada "
        "'?token=...' nya, token JWT-nya, atau link move2link.co."
    )


def api_call(method: str, path: str, token: str) -> dict:
    body = json.dumps(
        {"token": token, "csrf_token": CSRF_TOKEN, "imps": []}
    ).encode()
    req = urllib.request.Request(
        API + path,
        method=method,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Origin": "https://diary.siendu.com",
        },
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            raise ResolveError(
                f"API {method} {path} dijawab HTTP {e.code} — "
                "token kemungkinan sudah terpakai/kedaluwarsa. "
                "Minta token fresh dari log RedirectGuard."
            ) from e
        except (urllib.error.URLError, http.client.HTTPException,
                ConnectionError, TimeoutError) as e:
            last_err = e
            time.sleep(2)
    else:
        raise ResolveError(f"API {method} {path} gagal total: {last_err}")
    if data.get("status", {}).get("code") != 200:
        raise ResolveError(f"API {method} {path} gagal: {data}")
    return data["data"]


def resolve_from_token(token: str, locale: str = "id") -> dict:
    """Jalankan track 0..max-1 lalu finalize. Return info link final."""
    payload = json.loads(b64d(token.split(".")[1]))
    slug = payload.get("shortlink_slug", "?")
    pid = payload.get("pid", "")

    while True:
        payload = json.loads(b64d(token.split(".")[1]))
        step, max_step = int(payload["step"]), int(payload["max_step"])
        if step >= max_step - 1:
            break
        token = api_call("PUT", "/views/track", token)["token"]

    payload = json.loads(b64d(token.split(".")[1]))
    pid = payload.get("pid", pid)
    redirect_url = api_call("POST", "/views/finalize", token)["redirect_url"]

    to = base64.b64encode(redirect_url.encode()).decode()
    go_url = f"https://go.move2link.co/?to={to}&locale={locale}&pid={pid}"
    return {
        "slug": slug,
        "pid": pid,
        "locale": locale,
        "final_url": redirect_url,
        "go_url": go_url,
    }


def capture_token_via_browser(shortlink_url: str, timeout_s: int = 90) -> str:
    """Buka shortlink pakai Chromium headless, tangkap token dari network.

    Token tiba di URL diary.siendu.com/?token=... lewat redirect; JS
    halaman menghapusnya 1-3 detik kemudian, tapi request network-nya
    sudah terekam duluan — jadi kita tangkap di sana.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ResolveError(
            "Versi lite: browser (Chromium) tidak tersedia di image ini, "
            "jadi shortlink langsung tidak bisa dibuka otomatis. "
            "Paste URL diary / token JWT dari log RedirectGuard saja."
        ) from e

    found = {}

    def on_request(request):
        url = request.url
        if "diary.siendu.com" in url and "token=" in url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            if "token" in qs and "token" not in found:
                found["token"] = qs["token"][0]
                found["locale"] = qs.get("locale", [None])[0]

    def on_response(response):
        # Paywall terdeteksi dari URL-nya
        if "paywall.move2link.com" in response.url:
            found["paywall"] = response.url

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
            )
            page.on("request", on_request)
            page.on("response", on_response)
            page.goto(shortlink_url, wait_until="domcontentloaded",
                      timeout=timeout_s * 1000)
            # Tunggu sampai token ketangkap atau halaman settle
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if "token" in found or "paywall" in found:
                    break
                page.wait_for_timeout(1000)
            browser.close()
    except ResolveError:
        raise
    except Exception as e:
        raise ResolveError(
            f"Browser gagal membuka shortlink: {e}. "
            "Coba paste token dari log RedirectGuard."
        ) from e

    if "paywall" in found:
        raise ResolveError(
            "Link ini PAYWALL (bayar QRIS dulu baru token diterbitkan). "
            "Tidak bisa dilewati script — bayar manual atau minta link "
            "locker biasa."
        )
    if "token" not in found:
        raise ResolveError(
            "Token tidak ketangkap — kemungkinan Cloudflare memblokir "
            "browser server ini. Fallback: buka link di HP, lewati "
            "captcha, lalu paste URL diary dari log RedirectGuard."
        )
    return found["token"], found["locale"]


def resolve(raw: str) -> dict:
    """Satu pintu masuk: shortlink / URL diary / token mentah."""
    raw = raw.strip()
    m = SHORTLINK_RE.match(raw)
    if m:
        token, locale = capture_token_via_browser(raw)
        return resolve_from_token(token, locale or "id")
    token, locale = parse_input(raw)
    return resolve_from_token(token, locale or "id")
