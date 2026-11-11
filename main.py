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

from fastapi import FastAPI, Response, HTTPException
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


@app.middleware("http")
async def no_cache_for_pages(request, call_next):
    """Always serve the HTML pages fresh, so a new version shows up without a manual hard refresh."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store"
    return response

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
    logger.info(f"Starting WIPOTEC PV Certificate System v{read_version()}...")
    uvicorn.run(app, host="127.0.0.1", port=8000)