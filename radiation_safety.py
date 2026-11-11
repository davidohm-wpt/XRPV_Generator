"""X-Ray Radiation Safety Check (XRSC) certificate: form config, PDF template and routes."""
import logging
import traceback
from pathlib import Path
from typing import Dict
import weasyprint
from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, JSONResponse
from jinja2 import Template
from pydantic import BaseModel

from assets import LOGO_TOP_URI, LOGO_HEADER_URI, BASE_CSS, safe_filename_part, content_disposition

router = APIRouter()
logger = logging.getLogger("rs")
RS_HTML_PATH = Path(__file__).resolve().parent / "radiation_safety.html"

# Single source of truth for the checklist wording. The web form loads this via
# /rs-config, so names always match what the PDF template expects.
POWERED_DOWN = ["Documentation", "Cabinet", "Background Radiation Reading"]
POWERED_UP = ["Safety Interlock", "Alarm and Beacon Operations", "Radiation Levels", "Running Status"]
PART1 = [
    ("Warning Lights and Indicators", [
        'Warning label present at controls stating: "Caution: X-Rays Produced When Energized"',
        'Warning labels present at ports stating: "Caution: Do not insert any part of the body when system is energized, X-Ray hazard"',
        'Two indicators labelled "X-Ray ON" present at controls; and, at least one indicator, marked "X-Ray ON", is visible from each port, door and access panel',
    ]),
    ("Interlocks", [
        'The key for the Key Actuated Control cannot be removed in any mode that allows X-Ray generation',
        'All doors and access panels that were tested prevent generation of X-Rays',
        'The use of the "ON" control is necessary to resume operation of X-Rays following interruption of X-Ray generation',
    ]),
    ("Ports and Apertures", [
        'Check that a part of the body cannot be inserted through a "Port" or "Aperture" (e.g. Valve or Opening) into the Primary Beam, without the X-ray beam shutting down',
    ]),
]
POSITIONS = [str(n) for n in range(1, 11)]


class RSData(BaseModel):
    cert_no: str = ""
    check_date: str = ""
    local_regulation: str = ""
    customer_company_name: str = ""
    facility_name: str = ""
    street_address: str = ""
    country: str = ""
    zip_code: str = ""
    poc_name: str = ""
    poc_phone: str = ""
    poc_email: str = ""
    serial_no: str = ""
    manufacturer: str = "WIPOTEC"
    model: str = ""
    date_of_manufacture: str = ""
    location: str = ""
    label_attached: str = ""
    powered_down: Dict[str, Dict[str, str]] = {}
    powered_up: Dict[str, Dict[str, str]] = {}
    part1: Dict[str, str] = {}
    cabinet_condition: str = ""
    curtain_condition: str = ""
    other_comments: str = ""
    instrument_manufacturer: str = ""
    instrument_serial: str = ""
    instrument_model: str = ""
    calibration_due: str = ""
    kv_percent: str = ""
    ma_percent: str = ""
    max_limit: str = ""
    readings: Dict[str, str] = {}
    service_engineer: str = ""
    service_engineer_signature: str = ""
    customer_signature: str = ""
    remarks: str = ""


RS_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @page {
    size: A4; margin: 22mm 10mm 14mm 10mm;
    @top-left { content: "Certificate No: {{ cert_css }}"; font-family: Arial, sans-serif; font-size: 8pt; color: #333; vertical-align: bottom; padding-bottom: 5px; }
    @top-right { content: url('{{ logo_top }}'); vertical-align: bottom; padding-bottom: 5px; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: Arial, sans-serif; font-size: 8pt; color: #555; }
    @bottom-left { content: "WIPOTEC X-Ray Radiation Safety Check"; font-family: Arial, sans-serif; font-size: 7pt; color: #777; }
  }
  @page :first { margin-top: 12mm; @top-left { content: ""; } @top-right { content: ""; } }
  body { font-family: Arial, 'Sarabun', sans-serif; color: #1a1a1a; margin: 0; padding: 0; font-size: 8pt; line-height: 1.25; }
  {{ base_css }}
  .sub-head { font-weight: bold; color: #007777; font-size: 8pt; margin: 6px 0 2px; page-break-after: avoid; break-after: avoid; }
  .q-table td { vertical-align: top; }
  .ans-col { width: 55px; text-align: center; font-weight: bold; }
  .two-col { width: 100%; border-collapse: collapse; }
  .two-col > tbody > tr > td { width: 50%; vertical-align: top; padding: 0 2px; }
  .note { font-size: 7.5pt; margin: 4px 0; }
  .sig-box img { max-height: 50px; max-width: 90%; }
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

  <div class="doc-title"><span class="slash">/</span> X-Ray Radiation Safety</div>
  <table class="data-table" style="margin-bottom:6px;"><tr><td class="label-col">Certificate No.</td><td class="val-col"><strong>{{ data.cert_no }}</strong></td></tr></table>

  <table class="two-col"><tr><td>
    <div class="section-block">
      <div class="section-header"><span class="slash" style="color:#fff;">/</span> Customer</div>
      <table class="data-table">
        <tr><td class="label-col">Company Name</td><td class="val-col"><strong>{{ data.customer_company_name }}</strong></td></tr>
        <tr><td class="label-col">Facility Name</td><td class="val-col">{{ data.facility_name }}</td></tr>
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
        <tr><td class="label-col">Date of Manufacture</td><td class="val-col">{{ data.date_of_manufacture }}</td></tr>
        <tr><td class="label-col">Location</td><td class="val-col">{{ data.location }}</td></tr>
        <tr><td class="label-col">Manufacturer Certification Label Attached?</td><td class="val-col {{ cls(data.label_attached) }}">{{ data.label_attached }}</td></tr>
      </table>
    </div>
  </td></tr></table>

  {% for title, rows in [('Powered Down Checks', pd_rows), ('Powered Up Checks', pu_rows)] %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ title }}</div>
    <table class="checklist-table">
      <tr><th>Check</th><th class="ans-col" style="width:80px;">Initial Condition</th><th class="ans-col" style="width:80px;">As Left Condition</th><th>Comments</th></tr>
      {% for name, r in rows.items() %}
      <tr><td>{{ name }}</td>
        <td class="ans-col {{ cls(r.initial) }}">{{ r.initial }}</td>
        <td class="ans-col {{ cls(r.as_left) }}">{{ r.as_left }}</td>
        <td>{{ r.comments }}</td></tr>
      {% endfor %}
    </table>
  </div>
  {% endfor %}

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Part I: General Procedure Information</div>
    {% for group, qs in part1 %}
    <div class="sub-head">{{ group }}</div>
    <table class="checklist-table q-table">
      {% for q, ans in qs %}<tr><td>{{ q }}</td><td class="ans-col {{ cls(ans) }}">{{ ans }}</td></tr>{% endfor %}
    </table>
    {% endfor %}
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Part II: Specific Procedure Information</div>
    <table class="data-table">
      <tr><td class="label-col" style="width:60%;">Overall Condition of Cabinet X-Ray Unit</td><td class="val-col">{{ data.cabinet_condition }}</td></tr>
      <tr><td class="label-col">Condition of Curtains</td><td class="val-col">{{ data.curtain_condition }}</td></tr>
      <tr><td class="label-col">Other Comments, Recommendations, Corrections, or Problems Encountered</td><td class="val-col">{{ data.other_comments }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Radiation Survey</div>
    <table class="data-table">
      <tr><td class="label-col">Survey Instrument Manufacturer</td><td class="val-col">{{ data.instrument_manufacturer }}</td>
          <td class="label-col">Serial Number</td><td class="val-col">{{ data.instrument_serial }}</td></tr>
      <tr><td class="label-col">Model</td><td class="val-col">{{ data.instrument_model }}</td>
          <td class="label-col">Calibration Due Date</td><td class="val-col">{{ data.calibration_due }}</td></tr>
      <tr><td class="label-col">X-Ray Machine Settings</td><td class="val-col">{{ data.kv_percent }} % kV &nbsp;&nbsp; {{ data.ma_percent }} % mA</td>
          <td class="label-col">Highest Allowable External Surface Exposure Rate (Local Regulation)</td><td class="val-col"><strong>{{ data.max_limit }}</strong> &micro;Sv/hr</td></tr>
    </table>
    <div class="note"><strong>Note:</strong> All External Surface Exposure Rate readings are to be less than those stated as a maximum in the applicable Local Regulations.</div>
    <table class="checklist-table">
      <tr><th class="chk-col" style="width:60px;text-align:center;">Position</th><th>Reading (&micro;Sv/hr)</th><th class="chk-col" style="width:60px;text-align:center;">Position</th><th>Reading (&micro;Sv/hr)</th></tr>
      {% for a, b in reading_pairs %}
      <tr>
        <td class="chk-col">{{ a[0] }}</td><td class="{{ a[2] }}">{{ a[1] }}</td>
        <td class="chk-col">{{ b[0] if b else '' }}</td><td class="{{ b[2] if b else '' }}">{{ b[1] if b else '' }}</td>
      </tr>
      {% endfor %}
    </table>
    <div class="note"><strong>Survey Result:</strong> <span class="{{ survey_cls }}">{{ survey_text }}</span></div>
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Service Details & Remarks</div>
    <table class="data-table">
      <tr><td class="label-col" style="width:15%;">Safety Check Date</td><td class="val-col" style="width:35%;">{{ data.check_date }}</td>
          <td class="label-col" style="width:15%;">Local Regulation</td><td class="val-col" style="width:35%;">{{ data.local_regulation }}</td></tr>
      <tr><td class="label-col">Service Engineer</td><td class="val-col" colspan="3"><strong>{{ data.service_engineer }}</strong></td></tr>
      <tr><td class="label-col">Remarks</td><td class="val-col" colspan="3">{{ data.remarks }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <table class="signature-table"><tr>
      <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Service Engineer Signature</div>
        {% if data.service_engineer_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ data.service_engineer_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
        <div style="margin-top:3px;font-size:7.5pt;">( {{ data.service_engineer }} )</div></div></td>
      <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Customer Representative Signature</div>
        {% if data.customer_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ data.customer_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
        <div style="margin-top:3px;font-size:7.5pt;">( {{ data.poc_name }} )</div></div></td>
    </tr></table>
  </div>

  <div class="footer-text">
    <strong>Procedure:</strong> This certificate was completed with WIPOTEC-XR Work Instruction. Electronic original file stored securely.<br/>
    * X-Ray Radiation Safety Check Certificate.
  </div>
</body></html>
"""


def _cls(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("pass", "yes", "satisfactory", "✓"):
        return "pass-text"
    if v in ("fail", "no", "unsatisfactory", "✗"):
        return "fail-text"
    return "na-text"


def _num(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


@router.get("/radiation-safety.html")
def serve_rs_html():
    return FileResponse(RS_HTML_PATH)


@router.get("/rs-config")
def rs_config():
    return {
        "powered_down": POWERED_DOWN,
        "powered_up": POWERED_UP,
        "part1": [{"group": g, "questions": q} for g, q in PART1],
        "positions": POSITIONS,
    }


@router.post("/generate-rs-pdf")
def generate_rs_pdf(data: RSData):
    try:
        logger.info(f"Generate RS PDF requested for cert_no={data.cert_no!r}")
        pdf = _build_rs_pdf(data)
        logger.info(f"RS PDF generated successfully for cert_no={data.cert_no!r} ({len(pdf)} bytes)")
    except Exception as e:
        logger.error(f"RS PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500,
                            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"})
    name = f"XRSC_Certificate_{safe_filename_part(data.cert_no)}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(name)})


def _build_rs_pdf(data: RSData) -> bytes:
    blank ={"initial": "-", "as_left": "-", "comments": ""}
    pd_rows = {n: {**blank, **data.powered_down.get(n, {})} for n in POWERED_DOWN}
    pu_rows = {n: {**blank, **data.powered_up.get(n, {})} for n in POWERED_UP}
    part1 = [(g, [(q, data.part1.get(q, "-")) for q in qs]) for g, qs in PART1]

    limit = _num(data.max_limit)
    cells, over, filled = [], 0, 0
    for p in POSITIONS:
        raw = data.readings.get(p, "")
        val = _num(raw)
        cls = ""
        if val is not None:
            filled += 1
            if limit is not None:
                cls = "pass-text" if val < limit else "fail-text"
                over += val >= limit
        cells.append((p, raw, cls))
    half = (len(cells) + 1) // 2
    pairs = [(cells[i], cells[i + half] if i + half < len(cells) else None) for i in range(half)]
    if filled == 0 or limit is None:
        survey_text, survey_cls = "Not completed", "na-text"
    elif over:
        survey_text, survey_cls = f"FAIL - {over} reading(s) at or above the limit", "fail-text"
    else:
        survey_text, survey_cls = "PASS - all readings below the limit", "pass-text"

    cert_css = data.cert_no.replace("\\", "").replace('"', "").replace("\n", " ")
    html = Template(RS_TEMPLATE).render(
        data=(data.model_dump() if hasattr(data, "model_dump") else data.dict()), pd_rows=pd_rows, pu_rows=pu_rows, part1=part1,
        reading_pairs=pairs, survey_text=survey_text, survey_cls=survey_cls,
        cls=_cls, cert_css=cert_css, base_css=BASE_CSS,
        logo_top=LOGO_TOP_URI, logo_header=LOGO_HEADER_URI,
    )
    return weasyprint.HTML(string=html).write_pdf()
