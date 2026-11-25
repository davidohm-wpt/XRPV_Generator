"""X-Ray Comparison tool (moved in from the separate "X-Ray Compare Tools" program, v1.6.0).

The tool is a static web page in xray_compare/ (index.html, app.js, data.js, images),
served at /xr-compare/. Its "Export PDF" posts the comparison page to /api/pdf, which
prints it to PDF with Edge/Chrome in headless mode (same as the old program).
The headless browser has no sign-in cookie, so for the few seconds of a print job the
page and its pictures are served under /xr-compare-pdf/<random job id>/ instead
(see auth.OPEN_PREFIXES); the id is unguessable and only valid while the job runs.
"""
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

BASE_DIR = Path(__file__).resolve().parent
XR_DIR = (BASE_DIR / "xray_compare").resolve()
PDF_PREFIX = "/xr-compare-pdf/"
MAX_PAGE_BYTES = 5 * 1024 * 1024

logger = logging.getLogger("xr_compare")
router = APIRouter()
_jobs = {}   # job id -> page html (bytes), only while a PDF is being printed
_jobs_lock = threading.Lock()


def _file_in_xr_dir(rel: str) -> Path:
    rel = (rel or "").replace("\\", "/").lstrip("/") or "index.html"
    path = (XR_DIR / rel).resolve()
    if XR_DIR not in path.parents and path != XR_DIR:
        raise HTTPException(status_code=404)
    if path.is_dir():
        path = path / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404)
    return path


@router.get("/xr-compare")
def xr_root():
    return RedirectResponse("/xr-compare/", status_code=307)


@router.get("/xr-compare/{rel:path}")
def xr_file(rel: str):
    return FileResponse(_file_in_xr_dir(rel), headers={"Cache-Control": "no-store"})


@router.get(PDF_PREFIX + "{job}/{rel:path}")
def xr_pdf_file(job: str, rel: str):
    with _jobs_lock:
        page = _jobs.get(job)
    if page is None:
        raise HTTPException(status_code=404)
    if rel == "_page.html":
        return Response(page, media_type="text/html; charset=utf-8")
    return FileResponse(_file_in_xr_dir(rel))


def find_browser():
    """Path of Edge / Chrome, else None."""
    cands = []
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(var)
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
            cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    for name in ("msedge", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    return next((c for c in cands if os.path.isfile(c)), None)


@router.post("/api/pdf")
async def xr_pdf(request: Request):
    body = await request.body()
    if not body or len(body) > MAX_PAGE_BYTES:
        raise HTTPException(status_code=400, detail="Empty or too large page")
    return await _run_in_thread(_make_pdf, body, request.url.port or 8000)


async def _run_in_thread(fn, *args):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *args)


def _make_pdf(body: bytes, port: int) -> Response:
    browser = find_browser()
    if not browser:
        raise HTTPException(status_code=501, detail="No Edge/Chrome found")
    job = uuid.uuid4().hex
    base = f"http://127.0.0.1:{port}"
    # The page refers to its pictures with full addresses (http://127.0.0.1:PORT/xr-compare/...);
    # point them at the job folder, which works without a sign-in cookie.
    page = body.replace(f"{base}/xr-compare/".encode(), f"{base}{PDF_PREFIX}{job}/".encode())
    page = page.replace(f"http://localhost:{port}/xr-compare/".encode(), f"{base}{PDF_PREFIX}{job}/".encode())
    tmp = tempfile.mkdtemp(prefix="xr_pdf_")
    pdf_path = os.path.join(tmp, "out.pdf")
    profile = os.path.join(tmp, "profile")
    with _jobs_lock:
        _jobs[job] = page
    try:
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
               "--disable-extensions", "--no-pdf-header-footer", "--virtual-time-budget=10000",
               "--user-data-dir=" + profile, "--print-to-pdf=" + pdf_path,
               f"{base}{PDF_PREFIX}{job}/_page.html"]
        try:
            subprocess.run(cmd, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            logger.warning("Headless browser failed: %s", e)
        if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) < 500:
            raise HTTPException(status_code=500, detail="PDF not created")
        with open(pdf_path, "rb") as f:
            data = f.read()
        return Response(data, media_type="application/pdf")
    finally:
        with _jobs_lock:
            _jobs.pop(job, None)
        shutil.rmtree(tmp, ignore_errors=True)
