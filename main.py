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
GTK_BIN = BASE_DIR / "GTK3-Runtime" / "bin"

if GTK_BIN.exists():
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(GTK_BIN)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_HTML_PATH = BASE_DIR / "index.html"
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
    return FileResponse(INDEX_HTML_PATH)


@app.get("/index.html")
def serve_index_html():
    return FileResponse(INDEX_HTML_PATH)


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
  @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700&display=swap');

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

  *, *::before, *::after { box-sizing: border-box; }

  .page-logo {
    position: running(page-logo);
    width: 150px;
    height: auto;
    display: block;
  }

  body {
    font-family: Arial, 'Sarabun', sans-serif;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
    font-size: 8pt;
    line-height: 1.25;
  }

  .section-block, .data-table, .checklist-table, .signature-table, .product-card {
    page-break-inside: avoid;
    break-inside: avoid;
  }

  .section-header {
    background-color: #009999;
    color: #ffffff;
    padding: 3.5px 6px;
    font-size: 8.5pt;
    font-weight: bold;
    margin-top: 8px;
    margin-bottom: 3px;
    page-break-inside: avoid;
    break-inside: avoid;
    page-break-after: avoid;
    break-after: avoid;
  }

  .header-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 8px;
  }

  .company-info {
    font-size: 7.5pt;
    line-height: 1.2;
    color: #222;
  }

  .company-name {
    font-weight: bold;
    font-size: 8.5pt;
  }

  .logo-cell {
    text-align: right;
    vertical-align: top;
  }

  .logo-img {
    width: 150px;
    height: auto;
    display: inline-block;
  }

  .doc-title {
    font-size: 11pt;
    font-weight: bold;
    color: #000;
    margin-bottom: 8px;
  }

  .slash {
    color: #009999;
    font-weight: bold;
  }

  table.data-table, table.checklist-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 4px;
  }

  table.data-table td, table.data-table th, 
  table.checklist-table td, table.checklist-table th {
    border: 1px solid #c2d6d6;
    padding: 2.5px 5px;
    font-size: 7.5pt;
  }

  table.checklist-table th, table.data-table th {
    background-color: #009999;
    color: #ffffff;
    font-weight: bold;
    font-size: 7.5pt;
    text-align: left;
    border: 1px solid #008080;
  }

  .label-col {
    width: 32%;
    font-weight: bold;
    color: #333;
    background-color: #f2f8f8;
  }

  .val-col {
    color: #000000;
  }

  .chk-col {
    text-align: center;
    width: 45px;
    font-weight: bold;
  }

  .pass-text { color: #008000; font-weight: bold; }
  .fail-text { color: #cc0000; font-weight: bold; }
  .na-text { color: #666666; }

  .product-card {
    margin-bottom: 6px;
    border: 1px solid #c2d6d6;
    padding: 4px;
    background-color: #fafdfd;
  }

  .signature-table {
    width: 100%;
    margin-top: 10px;
    border-collapse: collapse;
  }

  .signature-table td {
    width: 50%;
    vertical-align: top;
    padding: 3px;
  }

  .sig-box {
    border: 1px solid #c2d6d6;
    border-top: 3px solid #009999;
    padding: 6px;
    text-align: center;
    background-color: #fafdfd;
  }

  .sig-line {
    margin-top: 24px;
    border-top: 1px solid #4a5568;
    width: 70%;
    margin-left: auto;
    margin-right: auto;
  }

  .footer-text {
    font-size: 7pt;
    color: #666;
    margin-top: 8px;
    border-top: 1px solid #ddd;
    padding-top: 4px;
    page-break-inside: avoid;
    break-inside: avoid;
  }
</style>
</head>
<body>

  <img class="page-logo" src="data:image/png;base64,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" alt="WIPOTEC">

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
        <img class="logo-img" src="data:image/png;base64,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" alt="WIPOTEC">
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
            layout=layout
        )
        
        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
        logger.info(f"PDF generated successfully for cert_no={data.cert_no!r} ({len(pdf_bytes)} bytes)")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=PV_Certificate_{data.cert_no}.pdf"}
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