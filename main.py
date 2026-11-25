import os
import ctypes
from pathlib import Path

# ============================================================
# GTK3 DLL Setup for Portable Mode
# ============================================================
# ปัญหา: WeasyPrint ใช้ cffi.dlopen() ซึ่งไม่เคารพ os.add_dll_directory()
#        เต็มรูปแบบ ทำให้ dependency chain ของ DLL ขาดตอนโหลด
# วิธีแก้: preload DLL ด้วย ctypes.CDLL() ตามลำดับ dependency
#        เพื่อให้ Windows resolve dependency chain ให้ครบก่อน
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
# Portable (embeddable) Python ignores the script folder on sys.path, so add it explicitly
# - otherwise sibling modules such as radiation_safety.py cannot be imported.
import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
GTK_BIN = BASE_DIR / "GTK3-Runtime" / "bin"

if GTK_BIN.exists():
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(GTK_BIN)
    # cffi resolves bare DLL names (e.g. "libgobject-2.0-0") by searching PATH. If another
    # GTK (e.g. C:\Program Files\GTK3-Runtime Win64\bin) is on PATH, a second copy of
    # gobject/pango gets loaded next to ours, GObject type registration breaks and
    # write_pdf() spins forever. Put the portable GTK first so only one copy is used,
    # also when main.py is started directly instead of via Run_PV.bat.
    os.environ["PATH"] = str(GTK_BIN) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(GTK_BIN))

    # Preload DLL ตามลำดับ dependency (สำคัญมาก: ห้ามสลับลำดับ)
    # เรียงจาก layer ล่างสุด (พื้นฐาน) ขึ้นไปหา layer บนสุด (pango/cairo)
    _preload_order = [
        # --- Layer 1: พื้นฐาน (ไม่พึ่ง DLL ตัวอื่นใน GTK) ---
        "libwinpthread-1.dll",
        "libgcc_s_seh-1.dll",
        "libiconv-2.dll",
        "libintl-8.dll",
        "libpcre-1.dll",
        "libffi-7.dll",
        "zlib1.dll",
        "libbz2-1.dll",
        "liblzma-5.dll",
        # --- Layer 2: glib ecosystem ---
        "libglib-2.0-0.dll",
        "libgmodule-2.0-0.dll",
        "libgthread-2.0-0.dll",
        "libgobject-2.0-0.dll",
        "libgio-2.0-0.dll",
        # --- Layer 3: cairo + image libs ---
        "libpng16-16.dll",
        "libjpeg-8.dll",
        "libtiff-5.dll",
        "libwebp-7.dll",
        "libpixman-1-0.dll",
        "libcairo-2.dll",
        "libcairo-gobject-2.dll",
        # --- Layer 4: font handling ---
        "libexpat-1.dll",
        "libfreetype-6.dll",
        "libfontconfig-1.dll",
        "libpango-1.0-0.dll",
        "libpangocairo-1.0-0.dll",
        "libpangoft2-1.0-0.dll",
        "libpangowin32-1.0-0.dll",
        # --- Layer 5: harfbuzz (สำหรับ text shaping) ---
        "libharfbuzz-0.dll",
        "libgraphite2.dll",
    ]

    _loaded = 0
    _failed = []
    for dll_name in _preload_order:
        dll_path = GTK_BIN / dll_name
        if dll_path.exists():
            try:
                ctypes.CDLL(str(dll_path))
                _loaded += 1
            except OSError as e:
                _failed.append(f"{dll_name}: {e}")
        # ถ้าไฟล์ไม่มีอยู่ ให้ข้ามไป (ไม่ใช่ทุกเวอร์ชันที่จะมีไฟล์ครบ)

    print(f"[GTK3] Preloaded {_loaded} DLLs from {GTK_BIN}")
    if _failed:
        print("[GTK3] Some DLLs failed to preload:")
        for msg in _failed:
            print(f"  - {msg}")

# ============================================================
# ตอนนี้ค่อย import weasyprint ได้ (หลัง GTK3 พร้อมแล้ว)
# ============================================================
import weasyprint

from fastapi import FastAPI, Response, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict
import logging
import traceback
from jinja2 import Template
from assets import LOGO_HEADER_URI, BASE_CSS, safe_filename_part, content_disposition
from radiation_safety import router as rs_router  # X-Ray Radiation Safety (XRSC) form + PDF
from preventive_maintenance import router as pm_router  # X-Ray Preventive Maintenance (PM) form + PDF
from cwcr import router as cwcr_router  # Checkweigher Calibration Report (CWCR) form + PDF
from commissioning import router as cwcq_router  # CW Commissioning & Qualification (CWCQ) form + PDF
from xray_installation import router as xriq_router  # X-Ray Installation & Qualification (XRIQ) form + PDF
import auth  # sign-in (users.json + local_accounts.json)
from xray_compare import router as xr_compare_router  # X-Ray Comparison tool (Tools section)

# --- Logging setup ---
LOG_PATH = BASE_DIR / "pv_server.log"

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("pv_server")

app = FastAPI()
app.include_router(rs_router)
app.include_router(pm_router)
app.include_router(cwcr_router)
app.include_router(cwcq_router)
app.include_router(xriq_router)
app.include_router(auth.router)
app.include_router(xr_compare_router)


# ============================================================
# Auto-exit: close the server (and its console window) when the user has closed
# every app page. Each page sends a heartbeat every 20 s and a "bye" when it is
# closed; the script is injected into every HTML page below, so pages synced from
# elsewhere do not need to carry it. Only armed after the first heartbeat, and only
# when main.py runs as the program (not when imported by tests).
# ============================================================
import threading
import time as _time

HEARTBEAT_SCRIPT = b"""<script>(function(){var id=Math.random().toString(36).slice(2);
function off(show){var b=document.getElementById('xrpv-off');if(!show){if(b)b.remove();return;}if(b)return;
b=document.createElement('div');b.id='xrpv-off';
b.textContent='The program has been closed. Open WIPOTEC AIO Software again to continue - what you typed on this page is kept.';
b.style.cssText='position:fixed;left:0;right:0;bottom:0;padding:10px 14px;background:#b02a37;color:#fff;font:14px Segoe UI,sans-serif;text-align:center;z-index:2147483647';
document.body.appendChild(b);}
function hb(){fetch('/heartbeat',{method:'POST',body:id,keepalive:true,cache:'no-store'}).then(function(r){off(!r.ok);}).catch(function(){off(true);});}
hb();setInterval(hb,20000);
document.addEventListener('visibilitychange',function(){if(!document.hidden)hb();});
addEventListener('pagehide',function(){try{navigator.sendBeacon('/bye',id);}catch(e){}});})();</script>"""

_AUTO_EXIT = {"armed": False, "clients": {}, "empty_since": None}
_AUTO_EXIT_LOCK = threading.Lock()
CLIENT_STALE_SECONDS = 150   # no heartbeat for this long = page is gone (browser crashed, PC off...)
EMPTY_GRACE_SECONDS = 10     # time to wait after the last page closed (covers moving between pages)


def _auto_exit_watchdog():
    last_loop = _time.monotonic()
    while True:
        _time.sleep(5)
        now = _time.monotonic()
        with _AUTO_EXIT_LOCK:
            if now - last_loop > 30:
                # The PC was asleep: give open pages a fresh start instead of shutting down.
                for k in _AUTO_EXIT["clients"]:
                    _AUTO_EXIT["clients"][k] = now
                _AUTO_EXIT["empty_since"] = None
            last_loop = now
            if not _AUTO_EXIT["armed"]:
                continue
            for k, seen in list(_AUTO_EXIT["clients"].items()):
                if now - seen > CLIENT_STALE_SECONDS:
                    del _AUTO_EXIT["clients"][k]
            if _AUTO_EXIT["clients"]:
                _AUTO_EXIT["empty_since"] = None
                continue
            if _AUTO_EXIT["empty_since"] is None:
                _AUTO_EXIT["empty_since"] = now
                continue
            if now - _AUTO_EXIT["empty_since"] < EMPTY_GRACE_SECONDS:
                continue
        logger.info("All app pages are closed - shutting down the server.")
        logging.shutdown()
        os._exit(0)


@app.post("/heartbeat")
async def heartbeat(request: Request):
    cid = (await request.body()).decode("utf-8", "ignore")[:64] or "anon"
    with _AUTO_EXIT_LOCK:
        _AUTO_EXIT["clients"][cid] = _time.monotonic()
        _AUTO_EXIT["armed"] = True
        _AUTO_EXIT["empty_since"] = None
    return {"ok": True}


@app.post("/bye")
async def bye(request: Request):
    cid = (await request.body()).decode("utf-8", "ignore")[:64]
    with _AUTO_EXIT_LOCK:
        _AUTO_EXIT["clients"].pop(cid, None)
    return {"ok": True}


@app.middleware("http")
async def no_cache_for_pages(request, call_next):
    """Always serve the HTML pages fresh (so a new version shows up without a hard refresh)
    and add the heartbeat script used by the auto-exit (plus the signed-in user box)."""
    response = await call_next(request)
    path = request.url.path
    tool_page = path.startswith("/xr-compare/")
    if path == "/" or path.endswith(".html") or path in ("/login", "/set-password") or tool_page:
        response.headers["Cache-Control"] = "no-store"
        if response.headers.get("content-type", "").startswith("text/html"):
            body = b"".join([chunk async for chunk in response.body_iterator])
            if b"</body>" in body:
                # The X-Ray Comparison page sends its own heartbeat (app.js).
                extra = auth.user_badge(request, tool_page) + (b"" if tool_page else HEARTBEAT_SCRIPT)
                body = body.replace(b"</body>", extra + b"</body>", 1)
            headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "etag")}
            return Response(content=body, status_code=response.status_code, headers=headers)
    return response

# Sign-in check (added after the middleware above, so it runs first). Only enforced when
# main.py runs as the program - see auth.ENABLED below.
app.middleware("http")(auth.guard)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_HTML_PATH = BASE_DIR / "index.html"
HOME_HTML_PATH = BASE_DIR / "home.html"
VERSION_FILE_PATH = BASE_DIR / "VERSION.txt"


def read_version() -> str:
    try:
        if VERSION_FILE_PATH.exists():
            return VERSION_FILE_PATH.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"Could not read VERSION.txt: {e}")
    return "unknown"


@app.get("/")
def serve_root():
    return FileResponse(HOME_HTML_PATH)


@app.get("/home.html")
def serve_home_html():
    return FileResponse(HOME_HTML_PATH)


@app.get("/index.html")
def serve_index_html():
    return FileResponse(INDEX_HTML_PATH)


FAVICON_PATH = BASE_DIR / "wipotec2.ico"


@app.get("/favicon.ico")
def serve_favicon():
    from fastapi.responses import Response
    if FAVICON_PATH.exists():
        return FileResponse(FAVICON_PATH, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/version")
def get_version():
    return {"version": read_version()}


class ProductSphere(BaseModel):
    sphere_type: str
    sphere_id: str
    sphere_size: str
    result: str


class ProductSpec(BaseModel):
    product_name: str
    product_number: str
    conveyor_speed: str
    number_of_passes: str
    spheres: List[ProductSphere]


class TestSampleItem(BaseModel):
    sample_description: str


class FullPVData(BaseModel):
    cert_no: str = ""
    pv_date: str = ""
    next_pv_due: str = ""
    customer_company_name: str = ""
    street_address: str = ""
    country: str = ""
    zip_code: str = ""
    poc_name: str = ""
    poc_phone: str = ""
    poc_email: str = ""
    serial_no: str = ""
    asset_number: str = ""
    model: str = ""
    number_of_beams: str = ""
    number_of_detectors: str = ""
    number_of_reject: str = ""
    xray_sets: Dict[str, str] = {}
    detectors: Dict[str, str] = {}
    pc_pod_sn: str = ""
    software_version: str = ""
    visual_inspection: Dict[str, str] = {}
    safety_checklist: Dict[str, str] = {}
    functional_checklist: Dict[str, str] = {}
    products: List[ProductSpec] = []
    test_samples: List[TestSampleItem] = []
    service_engineer: str = ""
    service_engineer_signature: str = ""
    customer_signature: str = ""
    remarks: str = ""


def to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def normalize_keys(d: dict) -> dict:
    return {str(k).strip(): v for k, v in d.items()}


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  /* Sarabun (Thai) is installed locally by Run_PV.bat - no web font import, so PDF
     generation never waits on the network. */
  @page {
    size: A4;
    margin: 22mm 10mm 12mm 10mm;

    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-family: Arial, sans-serif;
      font-size: 8pt;
      color: #555;
    }

    @top-right {
      content: element(page-logo);
      vertical-align: bottom;
      padding-bottom: 2px;
    }
  }

  @page :first {
    margin-top: 12mm;
    @top-right {
      content: "";
    }
  }

  {{ base_css }}
</style>
</head>
<body>

  <img class="page-logo" src="{{ logo_header }}" alt="WIPOTEC">

  <table class="header-table">
    <tr>
      <td class="company-info" style="width: 50%; vertical-align: top;">
        <div class="company-name">WIPOTEC Singapore Pte Ltd.</div>
        <div>25 International Business Park</div>
        <div>#03-29 German Centre</div>
        <div>Singapore 609916</div>
      </td>
      <td class="company-info" style="width: 20%; vertical-align: top;">
        <div>T +65 690 803 58</div>
        <div>service.sea@wipotec.com</div>
        <div>www.wipotec.com</div>
      </td>
      <td class="logo-cell" style="width: 30%;">
        <img class="logo-img" src="{{ logo_header }}" alt="WIPOTEC">
      </td>
    </tr>
  </table>

  <div class="doc-title">
    <span class="slash">/</span> X-Ray Performance Verification
  </div>

  <table class="data-table" style="margin-bottom: 6px;">
    <tr>
      <td class="label-col">Certificate / Order No.</td>
      <td class="val-col" colspan="3"><strong>{{ data.cert_no }}</strong></td>
    </tr>
  </table>

  {% macro customer_block() %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Customer</div>
    <table class="data-table">
      <tr><td class="label-col">Company Name</td><td class="val-col" colspan="3"><strong>{{ data.customer_company_name }}</strong></td></tr>
      <tr><td class="label-col">Address</td><td class="val-col" colspan="3">{{ data.street_address }}</td></tr>
      <tr><td class="label-col">Country</td><td class="val-col">{{ data.country }}</td><td class="label-col">ZIP Code</td><td class="val-col">{{ data.zip_code }}</td></tr>
      <tr><td class="label-col">Customer Name</td><td class="val-col">{{ data.poc_name }}</td><td class="label-col">Customer Phone</td><td class="val-col">{{ data.poc_phone }}</td></tr>
      <tr><td class="label-col">Customer Email</td><td class="val-col" colspan="3">{{ data.poc_email }}</td></tr>
    </table>
  </div>
  {% endmacro %}

  {% macro location_block() %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Machine Information</div>
    <table class="data-table">
      <tr><td class="label-col">Serial No.</td><td class="val-col"><strong>{{ data.serial_no }}</strong></td><td class="label-col">Asset Number</td><td class="val-col">{{ data.asset_number }}</td></tr>
      <tr><td class="label-col">Manufacturer</td><td class="val-col">WIPOTEC</td><td class="label-col">Model</td><td class="val-col">{{ data.model }}</td></tr>
      <tr><td class="label-col">No. of Beams</td><td class="val-col">{{ data.number_of_beams }}</td><td class="label-col">No. of Detectors</td><td class="val-col">{{ data.number_of_detectors }}</td></tr>
      <tr><td class="label-col">Software Ver.</td><td class="val-col">{{ data.software_version }}</td><td class="label-col">No. of Reject</td><td class="val-col">{{ data.number_of_reject }}</td></tr>
      {% for key, val in data.xray_sets.items() %}
      <tr><td class="label-col">X-Ray Set {{ key }} S/N</td><td class="val-col" colspan="3">{{ val }}</td></tr>
      {% endfor %}
      {% for key, val in data.detectors.items() %}
      <tr><td class="label-col">Detector {{ key }} S/N</td><td class="val-col" colspan="3">{{ val }}</td></tr>
      {% endfor %}
      <tr><td class="label-col">PC/POD S/N</td><td class="val-col" colspan="3">{{ data.pc_pod_sn }}</td></tr>
    </table>
  </div>
  {% endmacro %}

  {% macro mechanics_block() %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Mechanics & Visual</div>
    <table class="checklist-table">
      <tr><th>Components</th><th class="chk-col">Result</th></tr>
      {% for item, res in visual_inspection.items() %}
      <tr><td>{{ item }}</td><td class="chk-col {% if res == '✓' or res == 'PASS' %}pass-text{% elif res == 'N/A' or res == '-' %}na-text{% else %}fail-text{% endif %}">{{ res }}</td></tr>
      {% endfor %}
    </table>
  </div>
  {% endmacro %}

  {% macro safety_block() %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> System Safety</div>
    <table class="checklist-table">
      <tr><th>Components</th><th class="chk-col">Result</th></tr>
      {% for item, res in safety_checklist.items() %}
      <tr><td>{{ item }}</td><td class="chk-col {% if res == '✓' or res == 'PASS' %}pass-text{% elif res == 'N/A' or res == '-' %}na-text{% else %}fail-text{% endif %}">{{ res }}</td></tr>
      {% endfor %}
    </table>
  </div>
  {% endmacro %}

  {% macro functional_block() %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Functional Checklist</div>
    <table class="checklist-table">
      <tr><th>Components</th><th class="chk-col">Result</th></tr>
      {% for item, res in functional_checklist.items() %}
      <tr><td>{{ item }}</td><td class="chk-col {% if res == '✓' or res == 'PASS' %}pass-text{% elif res == 'N/A' or res == '-' %}na-text{% else %}fail-text{% endif %}">{{ res }}</td></tr>
      {% endfor %}
    </table>
  </div>
  {% endmacro %}

  {% set blocks = {
    'customer': customer_block,
    'location': location_block,
    'mechanics': mechanics_block,
    'safety': safety_block,
    'functional': functional_block
  } %}

  <div class="info-checklist-grid">
    <table style="width: 100%; border-collapse: collapse;">
      <tr>
        <td style="width: 50%; vertical-align: top; padding-right: 2px;">
          {% for name in layout.left %}{{ blocks[name]() }}{% endfor %}
        </td>
        <td style="width: 50%; vertical-align: top; padding-left: 2px;">
          {% for name in layout.right %}{{ blocks[name]() }}{% endfor %}
        </td>
      </tr>
    </table>
  </div>

  {% if data.products %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Product Specifications ({{ data.products|length }} Product{% if data.products|length > 1 %}s{% endif %})</div>
    {% for prod in data.products %}
    <div class="product-card">
      <table class="data-table" style="margin-bottom: 3px;">
        <tr>
          <td class="label-col" style="width:18%">Product Name</td><td class="val-col" style="width:32%"><strong>{{ prod.product_name }}</strong></td>
          <td class="label-col" style="width:18%">Product Number</td><td class="val-col" style="width:32%">{{ prod.product_number }}</td>
        </tr>
        <tr>
          <td class="label-col">Conveyor Speed</td><td class="val-col">{{ prod.conveyor_speed }}</td>
          <td class="label-col">No. of Passes</td><td class="val-col">{{ prod.number_of_passes }}</td>
        </tr>
      </table>
      
      {% if prod.spheres %}
      <table class="checklist-table">
        <tr>
          <th>Type</th>
          <th>ID</th>
          <th>Size</th>
          <th class="chk-col">Result</th>
        </tr>
        {% for sphere in prod.spheres %}
        <tr>
          <td>{{ sphere.sphere_type }}</td>
          <td>{{ sphere.sphere_id }}</td>
          <td>{{ sphere.sphere_size }}</td>
          <td class="chk-col {% if sphere.result == '✓' or sphere.result == 'PASS' %}pass-text{% elif sphere.result == 'N/A' or sphere.result == '-' %}na-text{% else %}fail-text{% endif %}">{{ sphere.result }}</td>
        </tr>
        {% endfor %}
      </table>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if data.test_samples %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Test Samples Certification</div>
    <table class="checklist-table">
      <tr>
        <th>Sample Description</th>
      </tr>
      {% for sample in data.test_samples %}
      <tr>
        <td>{{ sample.sample_description }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Service Details & Remarks</div>
    <table class="data-table">
      <tr>
        <td class="label-col" style="width: 15%;">PV Date</td><td class="val-col" style="width: 35%;">{{ data.pv_date }}</td>
        <td class="label-col" style="width: 15%;">Next PV Due</td><td class="val-col" style="width: 35%;">{{ data.next_pv_due }}</td>
      </tr>
      <tr><td class="label-col">Service Engineer</td><td class="val-col" colspan="3"><strong>{{ data.service_engineer }}</strong></td></tr>
      <tr><td class="label-col">Remarks</td><td class="val-col" colspan="3">{{ data.remarks }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <table class="signature-table">
      <tr>
        <td>
          <div class="sig-box">
            <div style="font-weight: bold; color: #009999;">Service Engineer Signature</div>
            {% if data.service_engineer_signature %}
            <div style="height: 50px; display: flex; align-items: flex-end; justify-content: center; margin-top: 6px;">
              <img src="{{ data.service_engineer_signature }}" style="max-height: 50px; max-width: 90%;" />
            </div>
            {% else %}
            <div class="sig-line"></div>
            {% endif %}
            <div style="margin-top: 3px; font-size: 7.5pt;">( {{ data.service_engineer }} )</div>
          </div>
        </td>
        <td>
          <div class="sig-box">
            <div style="font-weight: bold; color: #009999;">Customer Representative Signature</div>
            {% if data.customer_signature %}
            <div style="height: 50px; display: flex; align-items: flex-end; justify-content: center; margin-top: 6px;">
              <img src="{{ data.customer_signature }}" style="max-height: 50px; max-width: 90%;" />
            </div>
            {% else %}
            <div class="sig-line"></div>
            {% endif %}
            <div style="margin-top: 3px; font-size: 7.5pt;">( {{ data.poc_name }} )</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <div class="footer-text">
    <strong>Procedure:</strong> This certificate was completed with WIPOTEC-XR Work Instruction. Electronic original file stored securely.<br/>
    * Performance Verification Certificate.
  </div>

</body>
</html>
"""


@app.post("/generate-pdf")
def generate_pdf(data: FullPVData):
    try:
        logger.info(f"Generate PDF requested for cert_no={data.cert_no!r}")

        default_visual = {
            "Documentation Present": "-",
            "Cabinet Condition": "-",
            "Gaskets and Seals": "-",
            "Screws and Fittings": "-",
            "Door Seal": "-",
            "Cable Glands": "-",
            "Other External Cables": "-",
            "Curtain Condition": "-",
            "Belt Condition": "-"
        }
        
        default_safety = {
            "AC Power Input Test": "-",
            "DC Power Input Test": "-",
            "Safety Interlock Test": "-",
            "PC / POD Test": "-",
            "Emergency Stop": "-",
            "Warning Labels Present": "-",
            "Lamp Stack Test": "-",
            "Aperture Interlock": "-",
            "Beam Alignment": "-"
        }
        
        default_functional = {
            "Belt Tracking Test": "-",
            "Conveyor Speed Adjustments": "-",
            "Throughput Speed": "-",
            "Product Spacing": "-",
            "Reject Confirm": "-",
            "Consecutive Reject": "-",
            "Bin Full Sensor": "-",
            "Pack Sensor": "-",
            "Low Air Pressure Sensor": "-",
            "Encoder": "-",
            "Software Connectivity": "-"
        }

        merged_visual = {**default_visual, **normalize_keys(data.visual_inspection)}
        merged_safety = {**default_safety, **normalize_keys(data.safety_checklist)}
        merged_functional = {**default_functional, **normalize_keys(data.functional_checklist)}

        canonical_order = ['customer', 'location', 'mechanics', 'safety', 'functional']
        block_weights = {
            'customer': 5,
            'location': 5 + len(data.xray_sets) + len(data.detectors),
            'mechanics': 1 + len(merged_visual),
            'safety': 1 + len(merged_safety),
            'functional': 1 + len(merged_functional),
        }
        left_set, right_set = set(), set()
        left_total = right_total = 0
        for name in sorted(canonical_order, key=lambda n: block_weights[n], reverse=True):
            weight = block_weights[name]
            if left_total <= right_total:
                left_set.add(name)
                left_total += weight
            else:
                right_set.add(name)
                right_total += weight
        layout = {
            'left': [n for n in canonical_order if n in left_set],
            'right': [n for n in canonical_order if n in right_set],
        }

        template = Template(HTML_TEMPLATE)
        rendered_html = template.render(
            data=to_dict(data),
            visual_inspection=merged_visual,
            safety_checklist=merged_safety,
            functional_checklist=merged_functional,
            layout=layout,
            base_css=BASE_CSS,
            logo_header=LOGO_HEADER_URI,
        )
        
        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
        logger.info(f"PDF generated successfully for cert_no={data.cert_no!r} ({len(pdf_bytes)} bytes)")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": content_disposition(
                f"PV_Certificate_{safe_filename_part(data.cert_no, 'Document')}.pdf")}
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"}
        )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting WIPOTEC AIO Software v{read_version()}...")
    # Close the server by itself once the user has closed every app page.
    # Set XRPV_NO_AUTO_EXIT=1 to keep it running (e.g. for debugging).
    if os.environ.get("XRPV_NO_AUTO_EXIT") != "1":
        threading.Thread(target=_auto_exit_watchdog, name="auto-exit", daemon=True).start()
    # Everyone has to sign in (accounts: users.json, managed with Manage_Users.bat).
    auth.ENABLED = True
    uvicorn.run(app, host="127.0.0.1", port=8000)