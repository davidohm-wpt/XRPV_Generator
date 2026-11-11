"""X-Ray Preventive Maintenance (PM) report: form config, PDF template and routes."""
import logging
import traceback
from pathlib import Path
from typing import Dict, List
import weasyprint
from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, JSONResponse
from jinja2 import Template
from pydantic import BaseModel

from assets import LOGO_TOP_URI, LOGO_HEADER_URI, BASE_CSS, safe_filename_part, content_disposition

router = APIRouter()
logger = logging.getLogger("pm")
PM_HTML_PATH = Path(__file__).resolve().parent / "preventive_maintenance.html"

RESULT = ["-", "✓", "✗", "N/A"]
# Single source of truth for the checklist. The form loads it via /pm-config so the
# item names always match what the PDF expects.
PM_GROUPS = [
    {"name": "Technical Documentation", "adjusted": False, "items": ["Operator Manual", "Technical Manual", "Wiring Diagram"]},
    {"name": "Frame", "adjusted": True, "items": ["Support Frame", "Alignment", "Fixed Feet", "Castors"]},
    {"name": "Conveyor System", "adjusted": True, "items": [
        "Curtains", "Wear Strip", "Motor", "Encoder", "Gas Struts", "Signage", "Guide Rails", "Sensors",
        "Manifold (Pipeline Only)", "Clamps", "Gaskets / O-Rings", "Rollers", "Conveyor Belt"]},
    {"name": "Reject System", "adjusted": True, "items": ["Reject Device", "Reject Bin", "Sensors", "Reject Solenoid"]},
    {"name": "Safety Circuit & Controls", "adjusted": True, "items": ["Safety Circuit", "Door Mounted Controls"]},
    {"name": "Cabinet Exterior", "adjusted": True, "items": [
        "Cabinet Exterior", "General Ingress", "Door Mechanism", "Door Gaskets", "Glands & Cover Plates",
        "Bed Strip and Collimator Seals", "Signage"]},
    {"name": "Electrical & X-Ray System", "adjusted": True, "items": [
        "Electronic Components", "Cable Looms & Dressing", "Wiring", "Mains Isolator", "Collimator",
        "Lamp Stack Beacon", "HMI", "PC", "Air Conditioner / Dryer / Heater", "Generator", "Detector",
        "Cabinet Temperature", "Radiation Emission Check"]},
    {"name": "Air Supply", "adjusted": True, "items": ["Maintenance Unit", "Air Failure Detector", "Hoses & Connectors", "Pressure Monitoring"]},
    {"name": "Software", "adjusted": False, "items": [
        {"name": "Software Version", "options": ["-", "No Issues Reported", "Issues Reported"]},
        "Backup Creation"]},
]


def _norm_items(group):
    out = []
    for it in group["items"]:
        out.append(it if isinstance(it, dict) else {"name": it, "options": RESULT})
    return out


class PMData(BaseModel):
    doc_no: str = ""
    cert_date: str = ""
    next_service: str = ""
    customer_company_name: str = ""
    street_address: str = ""
    country: str = ""
    zip_code: str = ""
    poc_name: str = ""
    poc_phone: str = ""
    poc_email: str = ""
    serial_no: str = ""
    manufacturer: str = "WIPOTEC"
    model: str = ""
    software_version: str = ""
    asset_number: str = ""
    machine_voltage: str = ""
    location: str = ""
    date_of_manufacture: str = ""
    number_of_detectors: str = ""
    diode_size: str = ""
    detector_type: str = ""
    detector_width: str = ""
    detectors: Dict[str, Dict[str, str]] = {}
    number_of_generators: str = ""
    generator_wattage: str = ""
    generator_kv: str = ""
    generator_ma: str = ""
    generators: Dict[str, Dict[str, str]] = {}
    pc_pn: str = ""
    pc_sn: str = ""
    checks: Dict[str, Dict[str, Dict[str, str]]] = {}
    diagnostic_details: str = ""
    photos: List[Dict[str, str]] = []
    phase_out_year: str = ""
    spare_parts_available: str = ""
    maintenance_interval: str = ""
    pv_interval: str = ""
    care_contract: str = ""
    spare_parts_kits: str = ""
    user_training: str = ""
    system_upgrade: str = ""
    spare_wear_parts: str = ""
    system_replacement: str = ""
    device_ready: str = ""
    technician_name: str = ""
    technician_signature: str = ""
    customer_signature: str = ""
    remarks: str = ""


PM_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @page {
    size: A4; margin: 22mm 10mm 14mm 10mm;
    @top-left { content: "Document Number: {{ doc_css }}"; font-family: Arial, sans-serif; font-size: 8pt; color: #333; vertical-align: bottom; padding-bottom: 5px; }
    @top-right { content: url('{{ logo_top }}'); vertical-align: bottom; padding-bottom: 5px; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: Arial, sans-serif; font-size: 8pt; color: #555; }
    @bottom-left { content: "WIPOTEC X-Ray Preventive Maintenance Report"; font-family: Arial, sans-serif; font-size: 7pt; color: #777; }
  }
  @page :first { margin-top: 12mm; @top-left { content: ""; } @top-right { content: ""; } }
  body { font-family: Arial, 'Sarabun', sans-serif; color: #1a1a1a; margin: 0; padding: 0; font-size: 8pt; line-height: 1.25; }
  {{ base_css }}
  .res-col { width: 62px; text-align: center; font-weight: bold; }
  .two-col { width: 100%; border-collapse: collapse; }
  .two-col > tbody > tr > td { width: 50%; vertical-align: top; padding: 0 2px; }
  .photo-card { border: 1px solid #c2d6d6; padding: 5px; margin-bottom: 6px; background: #fafdfd; page-break-inside: avoid; break-inside: avoid; }
  .photo-card img { max-width: 100%; max-height: 230px; display: block; margin: 0 auto 4px; }
  .disclaimer { font-size: 6.5pt; color: #666; margin-top: 8px; line-height: 1.3; }
  .sig-box img { max-height: 50px; max-width: 90%; }
  .pre { white-space: pre-wrap; }
</style></head>
<body>
  <table class="header-table"><tr>
    <td class="company-info" style="width:50%;vertical-align:top;">
      <div class="company-name">WIPOTEC Singapore Pte Ltd.</div>
      <div>25 International Business Park</div><div>#03-29 German Centre</div><div>Singapore 609916</div></td>
    <td class="company-info" style="width:20%;vertical-align:top;">
      <div>T +65 690 803 58</div><div>service.sea@wipotec.com</div><div>www.wipotec.com</div></td>
    <td class="logo-cell" style="width:30%;"><img src="{{ logo_header }}" style="width:160px;height:auto;" alt="WIPOTEC" /></td>
  </tr></table>

  <div class="doc-title"><span class="slash">/</span> X-Ray Preventive Maintenance Report</div>
  <table class="data-table" style="margin-bottom:6px;"><tr><td class="label-col">Document Number</td><td class="val-col"><strong>{{ data.doc_no }}</strong></td></tr></table>

  <table class="two-col"><tr><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Customer</div>
      <table class="data-table">
        <tr><td class="label-col">Company Name</td><td class="val-col"><strong>{{ data.customer_company_name }}</strong></td></tr>
        <tr><td class="label-col">Address</td><td class="val-col">{{ data.street_address }}</td></tr>
        <tr><td class="label-col">Country</td><td class="val-col">{{ data.country }}</td></tr>
        <tr><td class="label-col">ZIP Code</td><td class="val-col">{{ data.zip_code }}</td></tr>
        <tr><td class="label-col">Customer Name</td><td class="val-col">{{ data.poc_name }}</td></tr>
        <tr><td class="label-col">Customer Phone</td><td class="val-col">{{ data.poc_phone }}</td></tr>
        <tr><td class="label-col">Customer Email</td><td class="val-col">{{ data.poc_email }}</td></tr>
      </table>
    </div>
  </td><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> System Identification</div>
      <table class="data-table">
        <tr><td class="label-col">Serial No.</td><td class="val-col"><strong>{{ data.serial_no }}</strong></td></tr>
        <tr><td class="label-col">Manufacturer</td><td class="val-col">{{ data.manufacturer }}</td></tr>
        <tr><td class="label-col">Model</td><td class="val-col">{{ data.model }}</td></tr>
        <tr><td class="label-col">Software Version</td><td class="val-col">{{ data.software_version }}</td></tr>
        <tr><td class="label-col">Asset Number</td><td class="val-col">{{ data.asset_number }}</td></tr>
        <tr><td class="label-col">Machine Voltage</td><td class="val-col">{{ data.machine_voltage }}</td></tr>
        <tr><td class="label-col">Location</td><td class="val-col">{{ data.location }}</td></tr>
        <tr><td class="label-col">Date of Manufacture</td><td class="val-col">{{ data.date_of_manufacture }}</td></tr>
      </table>
    </div>
  </td></tr></table>

  <table class="two-col"><tr><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Detector Details</div>
      <table class="data-table">
        <tr><td class="label-col">Number of Detectors</td><td class="val-col">{{ data.number_of_detectors }}</td></tr>
        <tr><td class="label-col">Detector Diode Size</td><td class="val-col">{{ data.diode_size }}</td></tr>
        <tr><td class="label-col">Detector Type</td><td class="val-col">{{ data.detector_type }}</td></tr>
        <tr><td class="label-col">Detector Width</td><td class="val-col">{{ data.detector_width }}</td></tr>
        {% for k, v in data.detectors.items() %}
        <tr><td class="label-col">Detector {{ k }} P/N</td><td class="val-col">{{ v.get('pn', '') }}</td></tr>
        <tr><td class="label-col">Detector {{ k }} S/N</td><td class="val-col">{{ v.get('sn', '') }}</td></tr>
        {% endfor %}
      </table>
    </div>
  </td><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Generator Details</div>
      <table class="data-table">
        <tr><td class="label-col">Number of Generators</td><td class="val-col">{{ data.number_of_generators }}</td></tr>
        <tr><td class="label-col">Generator Wattage</td><td class="val-col">{{ data.generator_wattage }}</td></tr>
        <tr><td class="label-col">Generator kV</td><td class="val-col">{{ data.generator_kv }}</td></tr>
        <tr><td class="label-col">Generator mA</td><td class="val-col">{{ data.generator_ma }}</td></tr>
        {% for k, v in data.generators.items() %}
        <tr><td class="label-col">Generator {{ k }} P/N</td><td class="val-col">{{ v.get('pn', '') }}</td></tr>
        <tr><td class="label-col">Generator {{ k }} S/N</td><td class="val-col">{{ v.get('sn', '') }}</td></tr>
        {% endfor %}
      </table>
    </div>
  </td></tr></table>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> PC / POD Details</div>
    <table class="data-table"><tr>
      <td class="label-col" style="width:20%;">PC / Integrated PC / POD P/N</td><td class="val-col" style="width:30%;">{{ data.pc_pn }}</td>
      <td class="label-col" style="width:20%;">PC / Integrated PC / POD S/N</td><td class="val-col" style="width:30%;">{{ data.pc_sn }}</td>
    </tr></table>
  </div>

  {% macro group_block(g) %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ g.name }}</div>
    <table class="checklist-table">
      <tr><th>{{ 'Component' if g.adjusted else 'Item' }}</th>{% if g.adjusted %}<th class="res-col">Adjusted</th>{% endif %}<th class="res-col" {% if not g.adjusted %}style="width:105px;"{% endif %}>Result</th></tr>
      {% for r in g.rows %}
      <tr><td>{{ r.name }}</td>{% if g.adjusted %}<td class="res-col">{{ r.adjusted }}</td>{% endif %}<td class="res-col {{ cls(r.result) }}">{{ r.result }}</td></tr>
      {% endfor %}
    </table>
  </div>
  {% endmacro %}

  <div class="doc-title" style="font-size:10pt;margin:6px 0 0;"><span class="slash">/</span> Maintenance Checklist</div>
  <table class="two-col"><tr>
    <td>{% for g in left %}{{ group_block(g) }}{% endfor %}</td>
    <td>{% for g in right %}{{ group_block(g) }}{% endfor %}</td>
  </tr></table>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Diagnostic Details</div>
    <table class="data-table"><tr><td class="val-col pre" style="min-height:30px;">{{ data.diagnostic_details }}</td></tr></table>
    {% for p in photos %}
    <div class="photo-card"><img src="{{ p.image }}" />{% if p.comment %}<div><strong>Comment:</strong> {{ p.comment }}</div>{% endif %}</div>
    {% endfor %}
  </div>

  <table class="two-col"><tr><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Service Recommendations</div>
      <table class="data-table">
        <tr><td class="label-col">Phase Out Year</td><td class="val-col">{{ data.phase_out_year }}</td></tr>
        <tr><td class="label-col">All Spare Parts Still Available</td><td class="val-col {{ cls(data.spare_parts_available) }}">{{ data.spare_parts_available }}</td></tr>
        <tr><td class="label-col">Recommended Maintenance Interval</td><td class="val-col">{{ data.maintenance_interval }}</td></tr>
        <tr><td class="label-col">Recommended Performance Verification Interval</td><td class="val-col">{{ data.pv_interval }}</td></tr>
      </table>
    </div>
  </td><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Service & Parts</div>
      <table class="data-table">
        <tr><td class="label-col">Care Contract</td><td class="val-col">{{ data.care_contract }}</td></tr>
        <tr><td class="label-col">Spare Parts Kits</td><td class="val-col">{{ data.spare_parts_kits }}</td></tr>
        <tr><td class="label-col">User Training</td><td class="val-col">{{ data.user_training }}</td></tr>
        <tr><td class="label-col">System Upgrade</td><td class="val-col">{{ data.system_upgrade }}</td></tr>
        <tr><td class="label-col">Spare or Wear Parts</td><td class="val-col">{{ data.spare_wear_parts }}</td></tr>
        <tr><td class="label-col">System Replacement</td><td class="val-col">{{ data.system_replacement }}</td></tr>
      </table>
    </div>
  </td></tr></table>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Closing Document</div>
    <table class="data-table">
      <tr><td class="label-col" style="width:20%;">Certificate Date</td><td class="val-col" style="width:30%;">{{ data.cert_date }}</td>
          <td class="label-col" style="width:20%;">Date of Next Service</td><td class="val-col" style="width:30%;">{{ data.next_service }}</td></tr>
      <tr><td class="label-col">Device Ready for Operation</td><td class="val-col {{ cls(data.device_ready) }}">{{ data.device_ready }}</td>
          <td class="label-col">Technician Name</td><td class="val-col"><strong>{{ data.technician_name }}</strong></td></tr>
      <tr><td class="label-col">Customer Name</td><td class="val-col" colspan="3">{{ data.poc_name }}</td></tr>
      <tr><td class="label-col">Remarks</td><td class="val-col pre" colspan="3">{{ data.remarks }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <table class="signature-table"><tr>
      <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Technician Signature</div>
        {% if data.technician_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ data.technician_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
        <div style="margin-top:3px;font-size:7.5pt;">( {{ data.technician_name }} )</div></div></td>
      <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Customer Representative Signature</div>
        {% if data.customer_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ data.customer_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
        <div style="margin-top:3px;font-size:7.5pt;">( {{ data.poc_name }} )</div></div></td>
    </tr></table>
  </div>

  <div class="disclaimer">
    This document is issued to record completion of the work performed by WIPOTEC on the subject device in accordance with agreed standards.
    It does not guarantee the continued performance of the subject device. Any measurements recorded are based on the subject device's
    performance at a given time as tested by WIPOTEC and, except where explicitly stated otherwise, do not express an opinion as to the
    sufficiency of any customer designed procedures used to test the device. This document is not a warranty, either implied or express.
    WIPOTEC expressly disclaims any liability arising from the use of the information in this document for any purpose other than as specified herein.
  </div>
  <div class="footer-text"><strong>Procedure:</strong> This report was completed with WIPOTEC-XR Work Instruction. Electronic original file stored securely.</div>
</body></html>
"""


def _cls(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("✓", "yes", "no issues reported", "pass"):
        return "pass-text"
    if v in ("✗", "no", "issues reported", "fail"):
        return "fail-text"
    return "na-text"


@router.get("/preventive-maintenance.html")
def serve_pm_html():
    return FileResponse(PM_HTML_PATH)


@router.get("/pm-config")
def pm_config():
    return {
        "groups": [{"name": g["name"], "adjusted": g["adjusted"], "items": _norm_items(g)} for g in PM_GROUPS]
    }


@router.post("/generate-pm-pdf")
def generate_pm_pdf(data: PMData):
    try:
        logger.info(f"Generate PM PDF requested for doc_no={data.doc_no!r}")
        pdf = _build_pm_pdf(data)
        logger.info(f"PM PDF generated successfully for doc_no={data.doc_no!r} ({len(pdf)} bytes)")
    except Exception as e:
        logger.error(f"PM PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500,
                            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"})
    name = f"PM_Report_{safe_filename_part(data.doc_no)}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(name)})


def _build_pm_pdf(data: PMData) -> bytes:
    groups = []
    for g in PM_GROUPS:
        sent = data.checks.get(g["name"], {})
        rows = []
        for it in _norm_items(g):
            s = sent.get(it["name"], {})
            rows.append({"name": it["name"], "adjusted": s.get("adjusted", "-") or "-", "result": s.get("result", "-") or "-"})
        groups.append({"name": g["name"], "adjusted": g["adjusted"], "rows": rows, "weight": 2 + len(rows)})

    # Split the groups (kept in document order) into two columns of similar height
    best_k, best_diff = 1, None
    for k in range(1, len(groups)):
        diff = abs(sum(g["weight"] for g in groups[:k]) - sum(g["weight"] for g in groups[k:]))
        if best_diff is None or diff < best_diff:
            best_k, best_diff = k, diff
    left, right = groups[:best_k], groups[best_k:]

    photos = [p for p in data.photos if str(p.get("image", "")).startswith("data:image/")]
    doc_css = data.doc_no.replace("\\", "").replace('"', "").replace("\n", " ")
    html = Template(PM_TEMPLATE).render(
        data=(data.model_dump() if hasattr(data, "model_dump") else data.dict()),
        left=left, right=right, photos=photos, cls=_cls, doc_css=doc_css, base_css=BASE_CSS,
        logo_top=LOGO_TOP_URI, logo_header=LOGO_HEADER_URI,
    )
    return weasyprint.HTML(string=html).write_pdf()
