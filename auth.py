"""Sign-in for WIPOTEC AIO Software.

Accounts are listed in users.json, which is shipped with the program updates, so the
maintainer can add, disable or reset an account for the whole team (Manage_Users.bat).
A new account starts with a temporary password; at the first sign-in the user must choose
their own password. That password is kept only on this PC, in local_accounts.json
(never pushed, survives updates). Resetting an account in users.json makes the
locally chosen password invalid again, so the user starts over with the new temporary one.

Passwords are stored as PBKDF2-SHA256 hashes only. Sessions live in memory and end when
the program closes. Sign-in is only enforced when main.py runs as the program
(main.py sets ENABLED), so test scripts that import it are not affected.
"""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from assets import LOGO_HEADER_URI

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.json"
LOCAL_FILE = BASE_DIR / "local_accounts.json"

ENABLED = False
COOKIE = "xrpv_session"
MIN_PASSWORD_LEN = 8
MAX_FAILS = 5
LOCK_SECONDS = 60
PBKDF2_ITERATIONS = 200_000

# Reachable without signing in.
OPEN_PATHS = {"/login", "/logout", "/set-password", "/heartbeat", "/bye", "/favicon.ico", "/version"}
# Checked by the route itself (X-Ray Comparison PDF print jobs, see xray_compare.py).
OPEN_PREFIXES = ("/xr-compare-pdf/",)

router = APIRouter()
_lock = threading.Lock()
_sessions = {}   # token -> {"user": str, "must_change": bool}
_fails = {}      # username -> (count, locked_until)


# ---------------- passwords ----------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # no 0/O, 1/l/I


def temp_password() -> str:
    """Random temporary password such as 'Kq7m-Xa3P-w9Rt' (easy to read out)."""
    return "-".join("".join(secrets.choice(TEMP_ALPHABET) for _ in range(4)) for _ in range(3))


def normalize_username(name: str) -> str:
    return (name or "").strip().lower()


def valid_username(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,31}", name or ""))


# ---------------- account files ----------------
def _read_json(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_users() -> dict:
    users = _read_json(USERS_FILE).get("users", {})
    return users if isinstance(users, dict) else {}


def load_local() -> dict:
    return _read_json(LOCAL_FILE)


def save_local_password(username: str, reset: int, password: str) -> None:
    with _lock:
        data = load_local()
        data[username] = {"reset": reset, "hash": hash_password(password)}
        _write_json(LOCAL_FILE, data)


def display_name(username: str) -> str:
    u = load_users().get(username) or {}
    return u.get("name") or username


# ---------------- roles ----------------
# user:       everyday use; changes in tools that need approval are sent as requests
# supervisor: also approves / rejects requests and saves changes directly
# developer:  everything, plus maintenance (e.g. importing reference files, resetting test data)
ROLES = ("user", "supervisor", "developer")
ROLE_LABELS = {"user": "User", "supervisor": "Supervisor", "developer": "Developer"}


def role_of(username: str) -> str:
    r = str((load_users().get(username) or {}).get("role", "user")).lower()
    return r if r in ROLES else "user"


def current_user(request: Request):
    """{"username", "name", "role"} of the signed-in user, or None. When sign-in is off
    (tests / imported module) a local developer is assumed."""
    if not ENABLED:
        return {"username": "local", "name": "Local user", "role": "developer"}
    sess = get_session(request)
    if not sess or sess["must_change"]:
        return None
    u = sess["user"]
    return {"username": u, "name": display_name(u), "role": role_of(u)}


# ---------------- sessions ----------------
def get_session(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with _lock:
        return _sessions.get(token)


def _new_session(username: str, must_change: bool) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = {"user": username, "must_change": must_change}
    return token


def _safe_next(target: str) -> str:
    target = target or "/"
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def _wants_page(request: Request) -> bool:
    path = request.url.path
    return request.method == "GET" and (path == "/" or path.endswith(".html") or "text/html" in request.headers.get("accept", ""))


async def guard(request: Request, call_next):
    """HTTP middleware: lets a request through only for a signed-in user."""
    if (not ENABLED or request.url.path in OPEN_PATHS or request.url.path.startswith(OPEN_PREFIXES)
            or request.method == "OPTIONS"):
        return await call_next(request)
    sess = get_session(request)
    if sess and not sess["must_change"]:
        if (load_users().get(sess["user"]) or {}).get("active", True):
            return await call_next(request)
        with _lock:
            _sessions.pop(request.cookies.get(COOKIE), None)
        sess = None
    nxt = request.url.path + (("?" + request.url.query) if request.url.query else "")
    if _wants_page(request):
        page = "/set-password" if sess else "/login"
        return RedirectResponse(f"{page}?next={quote(nxt, safe='')}", status_code=303)
    return JSONResponse(status_code=401, content={"detail": "Please sign in again (Close this page and open WIPOTEC AIO Software)."})


# ---------------- pages ----------------
PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - WIPOTEC AIO Software</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#eef4f4;font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a}}
.box{{width:380px;background:#fff;border-radius:10px;box-shadow:0 8px 30px rgba(0,60,60,.12);overflow:hidden}}
.bar{{height:5px;background:#009999}}
.in{{padding:28px 32px 26px}}
.logo{{height:34px;display:block;margin-bottom:6px}}
.sub{{color:#8c8c8c;margin:0 0 22px;font-size:14px}}
h1{{font-size:18px;font-weight:600;margin:0 0 6px}}
p.info{{font-size:13px;color:#555;margin:0 0 16px;line-height:1.45}}
label{{display:block;font-size:13px;color:#444;margin:12px 0 5px}}
input{{width:100%;padding:10px 12px;border:1px solid #c9d6d6;border-radius:6px;font-size:15px;font-family:inherit}}
input:focus{{outline:none;border-color:#009999;box-shadow:0 0 0 3px rgba(0,153,153,.15)}}
button{{width:100%;margin-top:20px;padding:11px;border:0;border-radius:6px;background:#009999;color:#fff;font-size:15px;font-weight:600;cursor:pointer;font-family:inherit}}
button:hover{{background:#007f7f}}
.err{{background:#fbeaec;color:#b02a37;border-radius:6px;padding:9px 12px;font-size:13px;margin-bottom:6px}}
.foot{{margin-top:18px;font-size:12px;color:#9aa;text-align:center}}
</style></head>
<body><div class="box"><div class="bar"></div><div class="in">
<img class="logo" src="{logo}" alt="WIPOTEC">
<p class="sub">AIO Software</p>
{body}
<div class="foot">{foot}</div>
</div></div></body></html>"""


def _page(title: str, body: str, foot: str = "Ask your administrator if you do not have an account.") -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=title, logo=LOGO_HEADER_URI, body=body, foot=foot),
                        headers={"Cache-Control": "no-store"})


def _login_page(next_url: str, error: str = "", username: str = "") -> HTMLResponse:
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    if not load_users():
        err = '<div class="err">No user accounts have been set up yet. Contact your administrator.</div>'
    body = f"""<h1>Sign in</h1>{err}
<form method="post" action="/login">
<input type="hidden" name="next" value="{html.escape(next_url)}">
<label for="u">Username</label><input id="u" name="username" value="{html.escape(username)}" autocomplete="username" autofocus required>
<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form>"""
    return _page("Sign in", body)


def _set_password_page(next_url: str, name: str, error: str = "") -> HTMLResponse:
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""
    body = f"""<h1>Choose your password</h1>
<p class="info">Welcome, {html.escape(name)}. Please choose your own password to replace the temporary one.
It is kept only on this PC.</p>{err}
<form method="post" action="/set-password">
<input type="hidden" name="next" value="{html.escape(next_url)}">
<label for="p1">New password (at least {MIN_PASSWORD_LEN} characters)</label><input id="p1" name="password" type="password" autocomplete="new-password" autofocus required>
<label for="p2">Repeat the new password</label><input id="p2" name="confirm" type="password" autocomplete="new-password" required>
<button type="submit">Save password</button></form>"""
    return _page("Choose your password", body, foot='<a href="/logout" style="color:#9aa">Cancel and sign out</a>')


async def _form(request: Request) -> dict:
    # Parsed by hand: Starlette's request.form() needs the extra python-multipart package.
    body = (await request.body()).decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _with_cookie(resp, token: str):
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
    return resp


@router.get("/login")
def login_form(next: str = "/"):
    return _login_page(_safe_next(next))


@router.post("/login")
async def login_submit(request: Request):
    f = await _form(request)
    next_url = _safe_next(f.get("next", "/"))
    raw_name = (f.get("username") or "").strip()
    username = normalize_username(raw_name)
    password = f.get("password") or ""

    now = time.monotonic()
    with _lock:
        count, until = _fails.get(username, (0, 0))
    if until > now:
        return _login_page(next_url, f"Too many wrong passwords. Try again in {int(until - now) + 1} seconds.", raw_name)

    user = load_users().get(username)
    ok, must_change = False, False
    if user and user.get("active", True):
        reset = int(user.get("reset", 1))
        local = load_local().get(username)
        if local and int(local.get("reset", 0)) == reset:
            ok = verify_password(password, local.get("hash", ""))
        else:
            ok = verify_password(password, user.get("temp", ""))
            must_change = ok
    elif user:
        return _login_page(next_url, "This account has been disabled. Contact your administrator.", raw_name)

    if not ok:
        with _lock:
            count += 1
            _fails[username] = (0, now + LOCK_SECONDS) if count >= MAX_FAILS else (count, 0)
        return _login_page(next_url, "Wrong username or password.", raw_name)

    with _lock:
        _fails.pop(username, None)
    token = _new_session(username, must_change)
    target = f"/set-password?next={quote(next_url, safe='')}" if must_change else next_url
    return _with_cookie(RedirectResponse(target, status_code=303), token)


@router.get("/set-password")
def set_password_form(request: Request, next: str = "/"):
    sess = get_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    return _set_password_page(_safe_next(next), display_name(sess["user"]))


@router.post("/set-password")
async def set_password_submit(request: Request):
    sess = get_session(request)
    if not sess:
        return RedirectResponse("/login", status_code=303)
    f = await _form(request)
    next_url = _safe_next(f.get("next", "/"))
    username = sess["user"]
    name = display_name(username)
    user = load_users().get(username)
    if not user or not user.get("active", True):
        return RedirectResponse("/logout", status_code=303)
    pw, confirm = f.get("password") or "", f.get("confirm") or ""
    if len(pw) < MIN_PASSWORD_LEN:
        return _set_password_page(next_url, name, f"The password must be at least {MIN_PASSWORD_LEN} characters.")
    if pw != confirm:
        return _set_password_page(next_url, name, "The two passwords are not the same.")
    if verify_password(pw, user.get("temp", "")):
        return _set_password_page(next_url, name, "Please choose a password that is different from the temporary one.")
    save_local_password(username, int(user.get("reset", 1)), pw)
    with _lock:
        sess["must_change"] = False
    return RedirectResponse(next_url, status_code=303)


@router.get("/logout")
def logout(request: Request):
    with _lock:
        _sessions.pop(request.cookies.get(COOKIE), None)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


def user_badge(request: Request, tool_page: bool = False) -> bytes:
    """Small "signed in as" box added to the app pages (empty when sign-in is off).
    Tool pages (which have their own buttons at the top) get it at the bottom left,
    with a link back to the menu (they also have a big Home button of their own)."""
    sess = get_session(request) if ENABLED else None
    signed_in = bool(sess and not sess["must_change"])
    if not signed_in and not tool_page:
        return b""
    link = 'color:#009999;text-decoration:none'
    where = "bottom:8px;left:10px" if tool_page else "top:8px;right:10px"
    parts = []
    if tool_page:
        parts.append(f'<a href="/" style="{link}">&#8592; Menu</a>')
    if signed_in:
        parts.append(f'&#128100; {html.escape(display_name(sess["user"]))} '
                     f'<span style="color:#8a9a9a">({ROLE_LABELS[role_of(sess["user"])]})</span>')
        parts.append(f'<a href="/logout" style="{link}">Sign out</a>')
    return (
        f'<div id="xrpv-user" style="position:fixed;{where};z-index:2147483646;'
        'background:rgba(255,255,255,.95);border:1px solid #cfdcdc;border-radius:14px;padding:3px 11px;'
        "font:12px 'Segoe UI',sans-serif;color:#555\">"
        + " &middot; ".join(parts) + "</div>"
        "<style>@media print{#xrpv-user{display:none}}</style>"
    ).encode("utf-8")
