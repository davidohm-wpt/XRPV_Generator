"""Spare Part On Hand (Tools section).

Moved in from the claude.ai prototype (Ver.0.5.1). The page (spare_part/index.html) keeps
all its screens; instead of the browser's own storage it now talks to this API, so the data
can later live on one central server without changing the page:

    GET  /api/spare/state                 everything the page needs + who is signed in
    POST /api/spare/files                 upload one attachment (raw body)
    GET  /api/spare/files/{id}            download an attachment
    POST /api/spare/requests              new request (or direct save for supervisor/developer)
    POST /api/spare/requests/{id}/{act}   approve | reject (supervisor+), cancel (own request)
    POST /api/spare/import                reference file parsed in the browser (developer)
    POST /api/spare/export-log            note a CSV export in the history
    POST /api/spare/reset                 clear all stock / requests / history (developer)

Roles come from the sign-in accounts (auth.py): user, supervisor, developer.
Data: <program folder>/spare_data/ (state.json + files/), or the folder in XRPV_SPARE_DATA.
"""
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import auth
from assets import content_disposition

BASE_DIR = Path(__file__).resolve().parent
PAGE_DIR = BASE_DIR / "spare_part"
SEED_FILE = PAGE_DIR / "seed.json"
DATA_DIR = Path(os.environ.get("XRPV_SPARE_DATA") or (BASE_DIR / "spare_data"))
STATE_FILE = DATA_DIR / "state.json"
FILES_DIR = DATA_DIR / "files"

COUNTRIES = ("SG", "TH", "MY", "IN", "VN")
TYPES = {"update": "Update quantity", "add": "Add new part", "delete": "Remove part"}
MAX_FILE_MB = 10
MAX_LOG = 5000

router = APIRouter()
_lock = threading.Lock()
_seed_cache = None


# ---------------- storage ----------------
def _seed():
    global _seed_cache
    if _seed_cache is None:
        _seed_cache = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return _seed_cache


def _empty_state():
    return {"stock": [], "reqs": [], "log": [], "imp": {"ref": [], "src": [], "map": []}, "files": {}}


def _load():
    try:
        if STATE_FILE.exists():
            st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            base = _empty_state()
            base.update({k: v for k, v in st.items() if k in base})
            return base
    except Exception:
        pass
    return _empty_state()


def _save(st):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def _ref_map(st):
    ref = {}
    for r in _seed()["ref"] + st["imp"]["ref"]:
        ref.setdefault(r["p"], r)
    return ref


def _src_map(st):
    src = {}
    for s in _seed()["src"] + st["imp"]["src"]:
        src[s["no"]] = s
    return src


# ---------------- helpers ----------------
def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _me(request: Request):
    me = auth.current_user(request)
    if not me:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return me


def can_approve(me):
    return me["role"] in ("supervisor", "developer")


def is_developer(me):
    return me["role"] == "developer"


def _who(me):
    return {"id": me["username"], "name": me["name"], "role": me["role"]}


def _blank(v):
    return "(blank)" if v in ("", None) else v


def fmt_change(r):
    if r["type"] == "add":
        return "New part: " + ", ".join(f"{c} {(r['ch']['q'].get(c) or ['', 0])[1] or 0}" for c in COUNTRIES)
    if r["type"] == "delete":
        return f"Remove part from stock (total {r['ch'].get('total', 0)})"
    return "; ".join(f"{c}: {_blank(o)} → {_blank(n)}" for c, (o, n) in (r["ch"].get("q") or {}).items())


def log_text(r):
    out = ""
    nr = r.get("newRef")
    if nr:
        out += f"Manual part: {nr['d']}" + (f" [{nr['a']}]" if nr.get("a") else "") + \
               (f" · {nr['g']}" if nr.get("g") else "") + \
               (f" · {nr['x'].replace(chr(10), '; ')}" if nr.get("x") else "") + " · "
    out += fmt_change(r)
    if r.get("note"):
        out += f" · Note: {r['note']}"
    att = r.get("att") or []
    if att:
        out += f" · {len(att)} file{'s' if len(att) > 1 else ''}: " + ", ".join(a["name"] for a in att)
    return out


def _add_log(st, me, action, p="", change="", rid="", status=""):
    st["log"].insert(0, {"t": _now(), "u": me["name"], "role": me["role"], "a": action,
                         "rid": rid, "p": p, "c": change, "st": status})
    del st["log"][MAX_LOG:]


def _next_id(st):
    n = max([int(r["id"][1:]) for r in st["reqs"] if r["id"][1:].isdigit()] or [0]) + 1
    return f"R{n:04d}"


def _stock_of(st, p):
    return next((s for s in st["stock"] if s["p"] == p), None)


def _pending_of(st, p):
    return next((r for r in st["reqs"] if r["p"] == p and r["status"] == "Pending"), None)


def _is_obsolete(ref):
    return bool(ref) and str(ref.get("n", "")).startswith("OBSOLETE")


def _apply(st, r):
    if r["type"] == "add":
        if r.get("newRef") and r["p"] not in _ref_map(st):
            nr = r["newRef"]
            st["imp"]["ref"].append({"p": r["p"], "d": nr["d"], "x": nr.get("x", ""), "a": nr.get("a", ""),
                                     "g": nr.get("g", ""), "n": f"Manual entry · {r['id']} by {r['by']['name']}"})
        if not _stock_of(st, r["p"]):
            st["stock"].insert(0, {"p": r["p"], "q": {c: (r["ch"]["q"].get(c) or ["", 0])[1] for c in COUNTRIES}})
    elif r["type"] == "update":
        s = _stock_of(st, r["p"])
        if s:
            for c, (_, n) in (r["ch"].get("q") or {}).items():
                s["q"][c] = n
    elif r["type"] == "delete":
        st["stock"] = [s for s in st["stock"] if s["p"] != r["p"]]


def _qty(v):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        n = 0
    return max(0, min(n, 999999))


def _clean(s, n=2000):
    return str(s or "").strip()[:n]


# ---------------- page ----------------
@router.get("/spare-part")
def page_root():
    return RedirectResponse("/spare-part/", status_code=307)


@router.get("/spare-part/")
def page():
    return FileResponse(PAGE_DIR / "index.html", headers={"Cache-Control": "no-store"})


@router.get("/spare-part/logo.png")
def logo():
    return FileResponse(PAGE_DIR / "logo.png", headers={"Cache-Control": "no-cache"})


# ---------------- API ----------------
@router.get("/api/spare/state")
def state(request: Request):
    me = _me(request)
    with _lock:
        st = _load()
    seed = _seed()
    files = st.pop("files")
    return JSONResponse({
        "me": {**_who(me), "label": auth.ROLE_LABELS[me["role"]],
               "canApprove": can_approve(me), "isDeveloper": is_developer(me)},
        "base": {"ref": seed["ref"], "src": seed["src"], "map": seed["map"]},
        **st,
        "fileCount": len(files),
    }, headers={"Cache-Control": "no-store"})


@router.post("/api/spare/files")
async def upload(request: Request):
    me = _me(request)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(body) > MAX_FILE_MB * 1048576:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_FILE_MB} MB.")
    name = _clean(unquote(request.headers.get("x-file-name", "file")), 200) or "file"
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name)
    ctype = _clean(request.headers.get("content-type", "application/octet-stream"), 100)
    fid = "F" + uuid.uuid4().hex[:16]
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    (FILES_DIR / fid).write_bytes(body)
    with _lock:
        st = _load()
        st["files"][fid] = {"name": name, "type": ctype, "size": len(body), "by": me["username"],
                            "t": _now(), "used": False}
        _save(st)
    return {"id": fid, "name": name, "type": ctype, "size": len(body)}


@router.get("/api/spare/files/{fid}")
def download(fid: str, request: Request):
    _me(request)
    if not re.fullmatch(r"F[0-9a-f]{16}", fid):
        raise HTTPException(status_code=404)
    with _lock:
        meta = _load()["files"].get(fid)
    path = FILES_DIR / fid
    if not meta or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type=meta["type"] or "application/octet-stream",
                        headers={"Content-Disposition": content_disposition(meta["name"]).replace("attachment", "inline")})


@router.post("/api/spare/requests")
async def new_request(request: Request):
    me = _me(request)
    data = await request.json()
    rtype = data.get("type")
    p = _clean(data.get("p"), 40)
    note = _clean(data.get("note"))
    if rtype not in TYPES:
        raise HTTPException(status_code=400, detail="Unknown request type.")
    if not p:
        raise HTTPException(status_code=400, detail="Enter a Part No.")
    with _lock:
        st = _load()
        ref = _ref_map(st)
        s = _stock_of(st, p)
        pend = _pending_of(st, p)
        if pend:
            raise HTTPException(status_code=409, detail=f"{pend['id']} by {pend['by']['name']} is still Pending for this part.")
        att = []
        for fid in data.get("att") or []:
            meta = st["files"].get(fid)
            if not meta or meta["by"] != me["username"] or meta.get("used"):
                raise HTTPException(status_code=400, detail="An attached file was not found - attach it again.")
            att.append({"id": fid, "name": meta["name"], "type": meta["type"], "size": meta["size"]})
        if len(att) > 5:
            raise HTTPException(status_code=400, detail="Up to 5 files per request.")
        if not att and not note:
            raise HTTPException(status_code=400, detail="Write a note explaining the change, or attach a file.")
        newq = data.get("q") or {}
        new_ref = None
        if rtype == "update":
            if not s:
                raise HTTPException(status_code=400, detail='This part is not in stock yet. Use "Add new part".')
            ch = {"q": {}}
            for c in COUNTRIES:
                if c in newq:
                    nv = _qty(newq[c])
                    if nv != _qty(s["q"].get(c, 0)):
                        ch["q"][c] = [_qty(s["q"].get(c, 0)), nv]
            if not ch["q"]:
                raise HTTPException(status_code=400, detail="No quantity changed.")
        elif rtype == "add":
            if s:
                raise HTTPException(status_code=400, detail='This part is already in stock. Use "Update quantity".')
            if _is_obsolete(ref.get(p)):
                raise HTTPException(status_code=400, detail=ref[p]["n"])
            if p not in ref:
                nr = data.get("newRef") or {}
                new_ref = {"d": _clean(nr.get("d"), 300), "a": nr.get("a") if nr.get("a") in ("A", "B", "C") else "",
                           "g": _clean(nr.get("g"), 120), "x": _clean(nr.get("x"), 1000)}
                if not new_ref["d"] and not att:
                    raise HTTPException(status_code=400, detail="Part not found. Add its details manually before submitting.")
                new_ref["d"] = new_ref["d"] or "(see attached file)"
            ch = {"q": {c: ["", _qty(newq.get(c, 0))] for c in COUNTRIES}}
        else:
            if not s:
                raise HTTPException(status_code=400, detail="This part is not in stock.")
            ch = {"total": sum(_qty(s["q"].get(c, 0)) for c in COUNTRIES)}
        direct = can_approve(me)
        r = {"id": _next_id(st), "t": _now(), "by": _who(me), "type": rtype, "p": p, "ch": ch, "note": note,
             "att": att, "status": "Complete" if direct else "Pending"}
        if new_ref:
            r["newRef"] = new_ref
        act = f"Saved by {auth.ROLE_LABELS[me['role']].lower()}"
        if direct:
            r["done"] = {"t": r["t"], "name": me["name"], "act": act}
            _apply(st, r)
        for a in att:
            st["files"][a["id"]]["used"] = True
        st["reqs"].append(r)
        _add_log(st, me, act if direct else "Request submitted", p,
                 ("" if rtype == "update" else TYPES[rtype] + " · ") + log_text(r), r["id"], r["status"])
        _save(st)
    return {"ok": True, "id": r["id"], "status": r["status"]}


@router.post("/api/spare/requests/{rid}/{act}")
def close_request(rid: str, act: str, request: Request):
    me = _me(request)
    if act not in ("approve", "reject", "cancel"):
        raise HTTPException(status_code=404)
    with _lock:
        st = _load()
        r = next((x for x in st["reqs"] if x["id"] == rid), None)
        if not r or r["status"] != "Pending":
            raise HTTPException(status_code=409, detail="This request is no longer Pending.")
        if act in ("approve", "reject") and not can_approve(me):
            raise HTTPException(status_code=403, detail="Only a Supervisor or Developer can approve or reject requests.")
        if act == "cancel" and r["by"]["id"] != me["username"]:
            raise HTTPException(status_code=403, detail="You can only cancel your own requests.")
        label = {"approve": "Approved", "reject": f"Rejected by {auth.ROLE_LABELS[me['role']].lower()}",
                 "cancel": "Canceled by requester"}[act]
        r["status"] = "Complete" if act == "approve" else "Canceled"
        r["done"] = {"t": _now(), "name": me["name"], "act": label}
        if act == "approve":
            _apply(st, r)
        _add_log(st, me, label, r["p"], fmt_change(r), r["id"], r["status"])
        _save(st)
    return {"ok": True, "status": r["status"]}


@router.post("/api/spare/import")
async def import_reference(request: Request):
    me = _me(request)
    if not is_developer(me):
        raise HTTPException(status_code=403, detail="Only a Developer can import reference files.")
    data = await request.json()
    fname = _clean(data.get("fname"), 200)
    parts = data.get("parts") or []
    meta = data.get("meta") or {}
    with _lock:
        st = _load()
        src = _src_map(st)
        dup = next((s for s in src.values() if s["f"].lower() == fname.lower()), None)
        if dup:
            _add_log(st, me, "Import rejected", "", f"{fname}: duplicate file name")
            _save(st)
            return JSONResponse(status_code=409, content={
                "detail": f"{fname}: duplicate file name (already imported on {dup['imp']}, {dup['no']}). Not imported."})
        if not parts:
            raise HTTPException(status_code=400, detail=f"{fname}: no part lines found in this file.")
        no = _clean(meta.get("no"), 60) or re.sub(r"\.pdf$", "", fname, flags=re.I)
        if no in src:
            _add_log(st, me, "Import rejected", "", f"{fname}: duplicate commission no. {no}")
            _save(st)
            return JSONResponse(status_code=409, content={
                "detail": f"{fname}: duplicate commission no. {no} (already imported from {src[no]['f']}). Not imported."})
        ref = _ref_map(st)
        added = 0
        for pt in parts:
            pid = _clean(pt.get("id"), 40)
            if not pid:
                continue
            if pid not in ref:
                r = {"p": pid, "d": _clean(pt.get("name"), 300), "x": _clean(pt.get("det"), 2000),
                     "a": pt.get("abc") if pt.get("abc") in ("A", "B", "C") else "", "g": _clean(pt.get("cat"), 120), "n": ""}
                st["imp"]["ref"].append(r)
                ref[pid] = r
                added += 1
            st["imp"]["map"].append([pid, no, _clean(pt.get("pos"), 20), _qty(pt.get("qty"))])
        st["imp"]["src"].append({
            "no": no, "f": fname, "t": "Spare parts catalogue (etk-e1)", "mt": _clean(meta.get("mt"), 80),
            "pn": _clean(meta.get("pn"), 120), "dd": _clean(meta.get("dd"), 40), "by": _clean(meta.get("by"), 80),
            "pg": _qty(data.get("pages")), "ln": len(parts), "u": len({pt.get("id") for pt in parts}),
            "imp": datetime.now().strftime("%Y-%m-%d")})
        _add_log(st, me, "Import file", "", f"{fname} ({no}): {len(parts)} part lines, {added} new P/N")
        _save(st)
    pn = _clean(meta.get("pn"), 120)
    return {"ok": True, "message": f"{fname}: imported {len(parts)} part lines from {no}{' (' + pn + ')' if pn else ''}; "
                                   f"{added} new part number{'' if added == 1 else 's'} added to Part Reference."}


@router.post("/api/spare/export-log")
async def export_log(request: Request):
    me = _me(request)
    data = await request.json()
    with _lock:
        st = _load()
        _add_log(st, me, "Export CSV", "", _clean(data.get("name"), 200))
        _save(st)
    return {"ok": True}


@router.post("/api/spare/reset")
def reset(request: Request):
    me = _me(request)
    if not is_developer(me):
        raise HTTPException(status_code=403, detail="Only a Developer can reset the data.")
    with _lock:
        st = _empty_state()
        _add_log(st, me, "Data reset", "", "All stock, requests, history, imports and files were cleared")
        _save(st)
        if FILES_DIR.is_dir():
            for f in FILES_DIR.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
    return {"ok": True}
