"""User Accounts page (Admin section) - the same jobs as Manage_Users.bat, in the program.

Only Developers see or use it; every API call checks the role on the server.
Changes are written to users.json on this PC. "Send to team" commits and pushes only
users.json to GitHub, so every PC gets the change the next time the program starts.

    GET  /admin/users                       the page
    GET  /api/me                            who is signed in (used by the home page)
    GET  /api/admin/users                   accounts + whether users.json still has to be sent
    POST /api/admin/users                   add {username, name, role} -> temporary password
    POST /api/admin/users/{u}/reset         new temporary password
    POST /api/admin/users/{u}/role          {role}
    POST /api/admin/users/{u}/active        {active}
    POST /api/admin/users/{u}/delete
    POST /api/admin/publish                 commit + push users.json
"""
import os
import subprocess
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

import auth

BASE_DIR = Path(__file__).resolve().parent
PAGE = BASE_DIR / "admin_users.html"
GIT = BASE_DIR / "PortableGit" / "bin" / "git.exe"

router = APIRouter()
_lock = threading.Lock()


def _developer(request: Request):
    me = auth.current_user(request)
    if not me:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    if me["role"] != "developer":
        raise HTTPException(status_code=403, detail="Only a Developer can manage user accounts.")
    return me


def _load():
    data = auth._read_json(auth.USERS_FILE)
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    return data


def _save(data):
    auth._write_json(auth.USERS_FILE, data)


def _get(data, username):
    u = data["users"].get(username)
    if not u:
        raise HTTPException(status_code=404, detail="No such account.")
    return u


def _developers(data, active_only=True):
    return [k for k, u in data["users"].items()
            if str(u.get("role", "user")).lower() == "developer" and (u.get("active", True) or not active_only)]


# ---------------- git (Send to team) ----------------
def _git(*args, timeout=60):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    r = subprocess.run([str(GIT), "-C", str(BASE_DIR), *args], capture_output=True, text=True, timeout=timeout,
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def publish_status():
    """{"pending": users.json differs from GitHub, "can": this PC can send, "why": reason if not}."""
    if not GIT.is_file() or not (BASE_DIR / ".git").exists():
        return {"pending": False, "can": False, "why": "Git is not available in this program folder."}
    try:
        rc, out = _git("status", "--porcelain", "--", "users.json", timeout=20)
        changed = bool(out.strip())
        rc2, branch = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=20)
        rc3, ahead = _git("rev-list", "--count", "origin/main..HEAD", "--", "users.json", timeout=20)
    except Exception as e:
        return {"pending": False, "can": False, "why": f"Git check failed: {e}"}
    pending = changed or (rc3 == 0 and ahead.strip() not in ("", "0"))
    branch = branch.strip()
    if branch != "main":
        return {"pending": pending, "can": False,
                "why": f'This program folder is on branch "{branch}", not main - send the change after merging.'}
    return {"pending": pending, "can": True, "why": ""}


@router.post("/api/admin/publish")
def publish(request: Request):
    me = _developer(request)
    with _lock:
        st = publish_status()
        if not st["can"]:
            raise HTTPException(status_code=409, detail=st["why"])
        if not st["pending"]:
            return {"ok": True, "message": "Nothing to send - the team already has these accounts."}
        rc, out = _git("status", "--porcelain", "--", "users.json")
        if out.strip():
            rc, out = _git("-c", f"user.name={me['username']}", "commit", "-m",
                           f"Update user accounts (by {me['name']})", "--", "users.json")
            if rc != 0:
                raise HTTPException(status_code=500, detail="Could not save the change in git: " + out.strip()[-300:])
        rc, out = _git("fetch", "-q", "origin", "main")
        if rc != 0:
            raise HTTPException(status_code=502, detail="Cannot reach GitHub - check the internet connection and try again.")
        rc, behind = _git("rev-list", "--count", "HEAD..origin/main")
        if rc == 0 and behind.strip() not in ("", "0"):
            rc, out = _git("rebase", "--autostash", "origin/main", timeout=120)
            if rc != 0:
                _git("rebase", "--abort")
                raise HTTPException(status_code=409, detail="GitHub has newer changes that could not be combined "
                                                            "automatically. Run Push.bat once, then try again.")
        rc, out = _git("push", "-q", "origin", "HEAD:main", timeout=120)
        if rc != 0:
            raise HTTPException(status_code=502, detail="GitHub did not accept the change (this PC may not have "
                                                        "permission to publish). Details: " + out.strip()[-300:])
    return {"ok": True, "message": "Sent. Every PC gets the new accounts the next time the program is opened."}


# ---------------- page + account API ----------------
@router.get("/admin/users")
def page(request: Request):
    me = auth.current_user(request)
    if not me or me["role"] != "developer":
        return RedirectResponse("/", status_code=303)
    return FileResponse(PAGE, headers={"Cache-Control": "no-store"})


@router.get("/api/me")
def who(request: Request):
    me = auth.current_user(request)
    if not me:
        raise HTTPException(status_code=401)
    return {**me, "label": auth.ROLE_LABELS[me["role"]]}


@router.get("/api/admin/users")
def list_users(request: Request):
    me = _developer(request)
    data = _load()
    local = auth.load_local()
    rows = []
    for k, u in sorted(data["users"].items()):
        lp = local.get(k)
        rows.append({"username": k, "name": u.get("name", k),
                     "role": str(u.get("role", "user")).lower() if str(u.get("role", "user")).lower() in auth.ROLES else "user",
                     "active": bool(u.get("active", True)),
                     "ownPassword": bool(lp and int(lp.get("reset", 0)) == int(u.get("reset", 1)))})
    return {"me": me["username"], "users": rows, "publish": publish_status()}


@router.post("/api/admin/users")
async def add_user(request: Request):
    _developer(request)
    body = await request.json()
    name = auth.normalize_username(body.get("username"))
    full = str(body.get("name") or "").strip()[:80] or name
    role = str(body.get("role") or "user").lower()
    if not auth.valid_username(name):
        raise HTTPException(status_code=400, detail="Username: use 2-32 letters, digits, dot, dash or underscore (e.g. john.smith).")
    if role not in auth.ROLES:
        raise HTTPException(status_code=400, detail="Unknown role.")
    pw = auth.temp_password()
    with _lock:
        data = _load()
        if name in data["users"]:
            raise HTTPException(status_code=409, detail="That username already exists.")
        data["users"][name] = {"name": full, "role": role, "active": True, "reset": 1, "temp": auth.hash_password(pw)}
        _save(data)
    return {"ok": True, "username": name, "temp": pw}


@router.post("/api/admin/users/{username}/{action}")
async def change_user(username: str, action: str, request: Request):
    me = _developer(request)
    body = {}
    if action in ("role", "active"):
        body = await request.json()
    with _lock:
        data = _load()
        u = _get(data, username)
        own = username == me["username"]
        result = {"ok": True}
        if action == "reset":
            pw = auth.temp_password()
            u["reset"] = int(u.get("reset", 1)) + 1
            u["temp"] = auth.hash_password(pw)
            result["temp"] = pw
        elif action == "role":
            role = str(body.get("role") or "").lower()
            if role not in auth.ROLES:
                raise HTTPException(status_code=400, detail="Unknown role.")
            if own and role != "developer":
                raise HTTPException(status_code=400, detail="You cannot lower your own role (you would lock yourself out of this page).")
            u["role"] = role
        elif action == "active":
            active = bool(body.get("active"))
            if own and not active:
                raise HTTPException(status_code=400, detail="You cannot disable your own account.")
            u["active"] = active
        elif action == "delete":
            if own:
                raise HTTPException(status_code=400, detail="You cannot delete your own account.")
            del data["users"][username]
        else:
            raise HTTPException(status_code=404)
        if not _developers(data):
            raise HTTPException(status_code=400, detail="At least one active Developer account must remain.")
        _save(data)
    return result
