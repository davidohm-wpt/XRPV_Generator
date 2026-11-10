"""CWCR - Checkweigher Calibration Report: calculation engine, PDF template and routes.

Merged into the XRPV Generator server from the standalone CWCR project (v1.0.6.2).
The page is served at /cwcr.html and the PDF endpoint is /cwcr/generate-pdf.
"""
import logging
import re
import traceback
from pathlib import Path

import weasyprint
from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse, Response
from jinja2 import Template

router = APIRouter()
logger = logging.getLogger("cwcr")
CWCR_HTML_PATH = Path(__file__).resolve().parent / "cwcr.html"
CWCR_VERSION = "1.0.6.2"


@router.get("/cwcr.html")
def serve_cwcr_html():
    return FileResponse(CWCR_HTML_PATH)


@router.get("/cwcr/version")
def get_cwcr_version():
    return {"version": CWCR_VERSION}


# ============================================================
# Calibration calculation engine
# Mirrors classify() / eMultiplier() / evalLoadTest() in the
# frontend's index.html exactly, so the printed PDF's Error/
# Result columns always match what the wizard showed on screen.
# ============================================================
def classify(measuring_range) -> str:
    try:
        return "XIII" if float(measuring_range) <= 10000 else "XII"
    except (TypeError, ValueError):
        return "XIII"


def e_multiplier(m, wc_class):
    try:
        m = float(m)
    except (TypeError, ValueError):
        return None
    if wc_class == "XIII":
        if 0 < m <= 500:
            return 1
        if 500 < m <= 2000:
            return 2
        if 2000 < m <= 10000:
            return 3
        return None
    else:
        if 0 < m <= 5000:
            return 1
        if 5000 < m <= 20000:
            return 2
        if 20000 < m <= 100000:
            return 3
        return None


def eval_load_test(test_load, reading, e_value, measuring_range):
    if test_load in (None, "") or reading in (None, ""):
        return {"error": None, "result": None}
    try:
        test_load = float(test_load)
        reading = float(reading)
        e_value = float(e_value)
    except (TypeError, ValueError):
        return {"error": None, "result": None}
    wc_class = classify(measuring_range)
    error = reading - test_load
    if test_load == 0:
        return {"error": error, "result": "PASS" if abs(error) <= e_value else "FAIL"}
    mult = e_multiplier(test_load, wc_class)
    if mult is None:
        return {"error": error, "result": "FAIL"}
    return {"error": error, "result": "PASS" if abs(error) <= mult * e_value else "FAIL"}


def fmt_num(v, decimals=None):
    if v in (None, ""):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if decimals is None:
        return f"{v:g}"
    try:
        return f"{v:.{int(decimals)}f}"
    except (TypeError, ValueError):
        return f"{v:g}"


def sanitize_filename_part(s) -> str:
    s = str(s or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", "_", s)
    return s or "NA"


def build_load_rows(rows, get_test_load, main_info, decimals):
    """rows: list of {testLoad?, reading} -> list with computed error/result, formatted."""
    e_value = main_info.get("eValue")
    measuring_range = main_info.get("measuringRange")
    unit = main_info.get("unit", "")
    out = []
    for i, row in enumerate(rows or []):
        test_load = get_test_load(row, i)
        calc = eval_load_test(test_load, row.get("reading"), e_value, measuring_range)
        out.append({
            "label": row.get("label", i + 1),
            "test_load": f"{fmt_num(test_load, decimals)} {unit}".strip(),
            "reading": f"{fmt_num(row.get('reading'), decimals)} {unit}".strip() if row.get("reading") not in (None, "") else "—",
            "error": f"{'+' if (calc['error'] or 0) >= 0 else ''}{fmt_num(calc['error'], decimals)} {unit}".strip() if calc["error"] is not None else "—",
            "result": calc["result"] or "—",
        })
    return out


# ============================================================
# HTML template — same visual language (WIPOTEC teal, section
# headers, data/checklist tables) as the XRPV Generator's PDF,
# rebuilt from scratch for the CWCR data shape.
# ============================================================
WIPOTEC_LOGO_B64 = "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"

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  /* Sarabun is installed locally by Run_CWCR.bat (see Sarabun-*.ttf next
     to this file) — no network font import, so PDF generation works
     fully offline. */
  @page {
    size: A4;
    margin: 22mm 10mm 12mm 10mm;
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: Arial, sans-serif; font-size: 8pt; color: #555; }
    @top-right { content: element(page-logo); vertical-align: bottom; padding-bottom: 2px; }
  }
  @page :first { margin-top: 12mm; @top-right { content: ""; } }
  *, *::before, *::after { box-sizing: border-box; }
  .page-logo { position: running(page-logo); width: 150px; height: auto; display: block; }
  body { font-family: Arial, 'Sarabun', sans-serif; color: #1a1a1a; margin: 0; padding: 0; font-size: 8pt; line-height: 1.25; }
  .section-block, .data-table, .checklist-table, .signature-table, .product-card { page-break-inside: avoid; break-inside: avoid; }
  .section-header { background-color: #009999; color: #ffffff; padding: 3.5px 6px; font-size: 8.5pt; font-weight: bold; margin-top: 8px; margin-bottom: 3px; page-break-after: avoid; break-after: avoid; }
  .sub-header { font-weight: bold; font-size: 8pt; color: #009999; margin: 6px 0 2px; }
  .header-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  .company-info { font-size: 7.5pt; line-height: 1.2; color: #222; }
  .company-name { font-weight: bold; font-size: 8.5pt; }
  .logo-cell { text-align: right; vertical-align: top; }
  .logo-img { width: 150px; height: auto; display: inline-block; }
  .doc-title { font-size: 11pt; font-weight: bold; color: #000; margin-bottom: 8px; }
  .slash { color: #009999; font-weight: bold; }
  table.data-table, table.checklist-table { width: 100%; border-collapse: collapse; margin-bottom: 4px; }
  table.data-table td, table.data-table th, table.checklist-table td, table.checklist-table th { border: 1px solid #c2d6d6; padding: 2.5px 5px; font-size: 7.5pt; }
  table.checklist-table th, table.data-table th { background-color: #009999; color: #ffffff; font-weight: bold; font-size: 7.5pt; text-align: left; border: 1px solid #008080; }
  .label-col { width: 24%; font-weight: bold; color: #333; background-color: #f2f8f8; }
  .val-col { color: #000000; }
  .chk-col { text-align: center; width: 60px; font-weight: bold; }
  .pass-text, .good-text { color: #008000; font-weight: bold; }
  .fail-text, .bad-text { color: #cc0000; font-weight: bold; }
  .na-text { color: #666666; }
  .product-card, .lane-card { margin-bottom: 6px; border: 1px solid #c2d6d6; padding: 4px; background-color: #fafdfd; }
  .lane-title { font-size: 9.5pt; font-weight: bold; color: #009999; margin: 10px 0 4px; border-bottom: 2px solid #009999; padding-bottom: 2px; }
  .signature-table { width: 100%; margin-top: 10px; border-collapse: collapse; }
  .signature-table td { width: 50%; vertical-align: top; padding: 3px; }
  .sig-box { border: 1px solid #c2d6d6; border-top: 3px solid #009999; padding: 6px; text-align: center; background-color: #fafdfd; }
  .sig-line { margin-top: 24px; border-top: 1px solid #4a5568; width: 70%; margin-left: auto; margin-right: auto; }
  .footer-text { font-size: 7pt; color: #666; margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px; }
</style>
</head>
<body>
  <img class="page-logo" src="data:image/png;base64,{{ logo }}" alt="WIPOTEC">
  <table class="header-table">
    <tr>
      <td class="company-info" style="width: 70%; vertical-align: top;">
        <div class="company-name">WIPOTEC Checkweigher Calibration Report</div>
        <div>Document No.: <strong>{{ m.documentNo or '—' }}</strong></div>
      </td>
      <td class="logo-cell" style="width: 30%;">
        <img class="logo-img" src="data:image/png;base64,{{ logo }}" alt="WIPOTEC">
      </td>
    </tr>
  </table>
  <div class="doc-title"><span class="slash">/</span> Calibration Report</div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Customer Info</div>
    <table class="data-table">
      <tr><td class="label-col">Company Name</td><td class="val-col" colspan="3"><strong>{{ m.companyName or '—' }}</strong></td></tr>
      <tr><td class="label-col">Address</td><td class="val-col" colspan="3">{{ m.address or '—' }}</td></tr>
      <tr><td class="label-col">Country</td><td class="val-col">{{ m.country or '—' }}</td><td class="label-col">ZIP Code</td><td class="val-col">{{ m.zipCode or '—' }}</td></tr>
      <tr><td class="label-col">Point of Contact</td><td class="val-col">{{ m.pocName or '—' }}</td><td class="label-col">Phone</td><td class="val-col">{{ m.pocPhone or '—' }}</td></tr>
      <tr><td class="label-col">Email</td><td class="val-col" colspan="3">{{ m.pocEmail or '—' }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Machine Info</div>
    <table class="data-table">
      <tr><td class="label-col">Serial No.</td><td class="val-col"><strong>{{ m.machineSerial or '—' }}</strong></td><td class="label-col">Model</td><td class="val-col">{{ m.machineModelType or '—' }}</td></tr>
      <tr><td class="label-col">Software Version</td><td class="val-col">{{ m.softwareVersion or '—' }}</td><td class="label-col">Model No.</td><td class="val-col">{{ m.modelNumber or '—' }}</td></tr>
      <tr><td class="label-col">Manufacturing Year</td><td class="val-col">{{ m.manufacturingYear or '—' }}</td><td class="label-col">Customer Asset No. / Location</td><td class="val-col">{{ m.location or '—' }}</td></tr>
      <tr><td class="label-col">Measuring Range</td><td class="val-col">{{ m.measuringRange or '—' }} {{ m.unit or '' }}</td><td class="label-col">Display Value</td><td class="val-col">{{ m.displayValue or '—' }} {{ m.unit or '' }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> WIPOTEC Test Kit Information</div>
    <table class="checklist-table">
      <tr><th>Equipment</th><th>Serial Number</th><th>Certificate No.</th><th>Cal. Date</th><th>Due Date</th></tr>
      {% for row in test_kit %}
      <tr><td>{{ row.equipment or '—' }}</td><td>{{ row.serial or '—' }}</td><td>{{ row.cert or '—' }}</td><td>{{ row.calDate or '—' }}</td><td>{{ row.dueDate or '—' }}</td></tr>
      {% endfor %}
    </table>
  </div>

  {% macro checklist_table(rows) %}
  <table class="checklist-table">
    <tr><th>Description</th><th class="chk-col">Result</th><th>Remark</th></tr>
    {% for row in rows %}
    <tr>
      <td>{{ row.description or '—' }}</td>
      <td class="chk-col {% if row.result == 'Good' %}good-text{% elif row.result in ['Bad','Failed'] %}bad-text{% else %}na-text{% endif %}">{{ row.result or 'N/A' }}</td>
      <td>{{ row.remark or '' }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endmacro %}

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> System Check List</div>
    {{ checklist_table(system_checklist) }}
    {% if additional_system_checklist %}
    <div class="sub-header">Additional System Checklist</div>
    {{ checklist_table(additional_system_checklist) }}
    {% endif %}
    {% if optional_checklist %}
    <div class="sub-header">Optional Check List</div>
    {{ checklist_table(optional_checklist) }}
    {% endif %}
  </div>

  {% for lane in lanes %}
  <div class="lane-title">{% if lanes|length > 1 %}Lane {{ lane.laneNo }} — {% endif %}Transportation Check List &amp; Weight Testing</div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Weigh Cell Info</div>
    <table class="data-table">
      <tr><td class="label-col">WC Type</td><td class="val-col">{{ lane.cw.wcType or '—' }}</td><td class="label-col">Serial Number</td><td class="val-col">{{ lane.cw.serialNumber or '—' }}</td></tr>
      <tr><td class="label-col">Unit</td><td class="val-col">{{ m.unit or '—' }}</td><td class="label-col">e value</td><td class="val-col">{{ m.eValue or '—' }} {{ m.unit or '' }}</td></tr>
      <tr><td class="label-col">Display Value</td><td class="val-col">{{ m.displayValue or '—' }} {{ m.unit or '' }}</td><td class="label-col">Dead Load</td><td class="val-col">{{ m.deadLoad or '—' }} {{ m.unit or '' }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Transportation System Check List</div>
    {{ checklist_table(lane.cw.checklist) }}
    {% if lane.cw.additionalChecklist %}
    <div class="sub-header">Additional System Checklist</div>
    {{ checklist_table(lane.cw.additionalChecklist) }}
    {% endif %}
  </div>

  {% macro load_table(rows) %}
  <table class="checklist-table">
    <tr><th>No.</th><th>Test Load</th><th>Reading</th><th>Error</th><th class="chk-col">Result</th></tr>
    {% for row in rows %}
    <tr>
      <td>{{ row.label }}</td><td>{{ row.test_load }}</td><td>{{ row.reading }}</td><td>{{ row.error }}</td>
      <td class="chk-col {% if row.result == 'PASS' %}pass-text{% elif row.result == 'FAIL' %}fail-text{% else %}na-text{% endif %}">{{ row.result }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endmacro %}

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Linearity Test</div>
    {{ load_table(lane.cw.linearity_rows) }}
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Eccentricity Test</div>
    {{ load_table(lane.cw.eccentricity_rows) }}
  </div>

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Repeatability Test</div>
    {{ load_table(lane.cw.repeatability_rows) }}
  </div>

  {% if lane.cw.dynamicTests %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Product Dynamic Test / Spot Check</div>
    {% for d in lane.cw.dynamicTests %}
    <div class="product-card">
      <table class="data-table" style="margin-bottom: 3px;">
        <tr><td class="label-col" style="width:18%">Article Name</td><td class="val-col" style="width:32%"><strong>{{ d.articleName or '—' }}</strong></td><td class="label-col" style="width:18%">Article Number</td><td class="val-col" style="width:32%">{{ d.articleNumber or '—' }}</td></tr>
        <tr><td class="label-col">Dimension (L×W×H mm)</td><td class="val-col">{{ d.length or '—' }} × {{ d.width or '—' }} × {{ d.height or '—' }}</td><td class="label-col">Filter Frequency</td><td class="val-col">{{ d.filterFrequency or '—' }} Hz</td></tr>
        <tr><td class="label-col">Speed</td><td class="val-col">{{ d.speedValue or '—' }} {{ d.speedType or '' }}</td><td class="label-col">Quantity Test</td><td class="val-col">{{ d.qtyTest or '—' }}</td></tr>
        <tr><td class="label-col">Product Weight</td><td class="val-col">{{ d.productWeight or '—' }} {{ m.unit or '' }}</td><td class="label-col">Mean Value</td><td class="val-col">{{ d.meanValue or '—' }} {{ m.unit or '' }}</td></tr>
        <tr><td class="label-col">Standard Deviation</td><td class="val-col" colspan="3">{{ d.stdDeviation or '—' }} {{ m.unit or '' }}</td></tr>
      </table>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="section-block">
    <table class="data-table">
      <tr><td class="label-col">{% if lanes|length > 1 %}Lane {{ lane.laneNo }} {% endif %}Operate in Good Condition</td>
          <td class="val-col {% if lane.cw.operateGoodCondition == 'Yes' %}good-text{% elif lane.cw.operateGoodCondition == 'No' %}bad-text{% endif %}"><strong>{{ lane.cw.operateGoodCondition or '—' }}</strong></td></tr>
    </table>
  </div>

  {% if lane.md %}
  <div class="lane-title">{% if lanes|length > 1 %}Lane {{ lane.laneNo }} — {% endif %}Metal Detector Check List &amp; Testing</div>
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Metal Detector Info</div>
    <table class="data-table">
      <tr><td class="label-col">Model Type</td><td class="val-col">{{ lane.md.mdType or '—' }}</td><td class="label-col">Serial Number</td><td class="val-col">{{ lane.md.serialNumber or '—' }}</td></tr>
      <tr><td class="label-col">Tunnel Height</td><td class="val-col">{{ lane.md.tunnelHeight or '—' }} mm</td><td class="label-col">Tunnel Width</td><td class="val-col">{{ lane.md.tunnelWidth or '—' }} mm</td></tr>
    </table>
  </div>
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Physical Check List</div>
    {{ checklist_table(lane.md.checklist) }}
    {% if lane.md.additionalPhysicalChecklist %}
    <div class="sub-header">Additional Physical Check List</div>
    {{ checklist_table(lane.md.additionalPhysicalChecklist) }}
    {% endif %}
  </div>
  {% if lane.md.articles %}
  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Detection Verification</div>
    {% for art in lane.md.articles %}
    <div class="product-card">
      <table class="data-table" style="margin-bottom: 3px;">
        <tr><td class="label-col" style="width:18%">Article Name</td><td class="val-col" style="width:32%"><strong>{{ art.linked_name or '—' }}</strong></td><td class="label-col" style="width:18%">Article No.</td><td class="val-col" style="width:32%">{{ art.linked_number or '—' }}</td></tr>
        <tr><td class="label-col">Detection Level</td><td class="val-col">{{ art.detectionLevel or '—' }}</td><td class="label-col">Phase Angle</td><td class="val-col">{{ art.phaseAngle or '—' }}</td></tr>
        <tr><td class="label-col">Stretching</td><td class="val-col" colspan="3">{{ art.stretching or '—' }}</td></tr>
      </table>
      <table class="checklist-table">
        <tr><th>Type</th><th>ID</th><th>Size (mm)</th><th class="chk-col">Front</th><th class="chk-col">Middle</th><th class="chk-col">Back</th></tr>
        {% for mat_label, mat in [('Ferrous', art.ferrous), ('Non-Ferrous', art.nonFerrous), ('Stainless Steel 304', art.stainless)] %}
        <tr>
          <td>{{ mat_label }}</td><td>{{ mat.id or '—' }}</td><td>{{ mat.size or '—' }}</td>
          <td class="chk-col {% if mat.front == '✓' %}pass-text{% elif mat.front == '✗' %}fail-text{% else %}na-text{% endif %}">{{ mat.front or 'N/A' }}</td>
          <td class="chk-col {% if mat.middle == '✓' %}pass-text{% elif mat.middle == '✗' %}fail-text{% else %}na-text{% endif %}">{{ mat.middle or 'N/A' }}</td>
          <td class="chk-col {% if mat.back == '✓' %}pass-text{% elif mat.back == '✗' %}fail-text{% else %}na-text{% endif %}">{{ mat.back or 'N/A' }}</td>
        </tr>
        {% endfor %}
        {% for et in art.extraTypes %}
        {% if et.type %}
        <tr>
          <td>{{ et.type }}</td><td>{{ et.id or '—' }}</td><td>{{ et.size or '—' }}</td>
          <td class="chk-col {% if et.front == '✓' %}pass-text{% elif et.front == '✗' %}fail-text{% else %}na-text{% endif %}">{{ et.front or 'N/A' }}</td>
          <td class="chk-col {% if et.middle == '✓' %}pass-text{% elif et.middle == '✗' %}fail-text{% else %}na-text{% endif %}">{{ et.middle or 'N/A' }}</td>
          <td class="chk-col {% if et.back == '✓' %}pass-text{% elif et.back == '✗' %}fail-text{% else %}na-text{% endif %}">{{ et.back or 'N/A' }}</td>
        </tr>
        {% endif %}
        {% endfor %}
      </table>
    </div>
    {% endfor %}
  </div>
  {% endif %}
  {% endif %}
  {% endfor %}

  <div class="section-block">
    <div class="section-header"><span class="slash" style="color:#fff;">/</span> Summary</div>
    <table class="data-table">
      <tr><td class="label-col">Machine Operate in Good Condition</td>
          <td class="val-col {% if fr.machineGoodCondition == 'Yes' %}good-text{% elif fr.machineGoodCondition == 'No' %}bad-text{% endif %}" colspan="3"><strong>{{ fr.machineGoodCondition or '—' }}</strong></td></tr>
      <tr><td class="label-col">Additional Service Comments</td><td class="val-col" colspan="3">{{ fr.additionalComments or '—' }}</td></tr>
    </table>
  </div>

  <div class="section-block">
    <table class="signature-table">
      <tr>
        <td>
          <div class="sig-box">
            <div style="font-weight: bold; color: #009999;">Customer Signature</div>
            {% if fr.customer.signatureDataUrl %}
            <div style="height: 50px; display: flex; align-items: flex-end; justify-content: center; margin-top: 6px;">
              <img src="{{ fr.customer.signatureDataUrl }}" style="max-height: 50px; max-width: 90%;" />
            </div>
            {% else %}
            <div class="sig-line"></div>
            {% endif %}
            <div style="margin-top: 3px; font-size: 7.5pt;">( {{ fr.customer.name or '' }} )</div>
            <div style="font-size: 7pt; color:#666;">{{ fr.customer.date or '' }}</div>
          </div>
        </td>
        <td>
          <div class="sig-box">
            <div style="font-weight: bold; color: #009999;">Service Technician Signature</div>
            {% if fr.technician.signatureDataUrl %}
            <div style="height: 50px; display: flex; align-items: flex-end; justify-content: center; margin-top: 6px;">
              <img src="{{ fr.technician.signatureDataUrl }}" style="max-height: 50px; max-width: 90%;" />
            </div>
            {% else %}
            <div class="sig-line"></div>
            {% endif %}
            <div style="margin-top: 3px; font-size: 7.5pt;">( {{ fr.technician.name or '' }} )</div>
            <div style="font-size: 7pt; color:#666;">{{ fr.technician.date or '' }}</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <div class="footer-text">
    <strong>CWCR — Checkweigher Calibration Report.</strong> Generated by the WIPOTEC Calibration Report Generator.
  </div>
</body>
</html>
"""


def build_pdf_context(payload: dict) -> dict:
    m = dict(payload.get("mainInfo") or {})
    decimals = m.get("decimal")
    lanes_in = payload.get("lanes") or []
    lanes_out = []
    for lane in lanes_in:
        cw = dict(lane.get("cw") or {})
        lin_rows = build_load_rows(
            cw.get("linearity", {}).get("rows"),
            lambda row, i: row.get("testLoad"),
            m, decimals
        )
        ecc = cw.get("eccentricity", {}) or {}
        ecc_rows_raw = ecc.get("rows") or []
        for r in ecc_rows_raw:
            r["label"] = r.get("pos", "")
        ecc_rows = build_load_rows(ecc_rows_raw, lambda row, i: ecc.get("testLoad"), m, decimals)
        rep = cw.get("repeatability", {}) or {}
        rep_rows_raw = rep.get("rows") or []
        for i, r in enumerate(rep_rows_raw):
            r["label"] = (i // 2) + 1 if i % 2 == 0 else ""
        rep_rows = build_load_rows(
            rep_rows_raw,
            lambda row, i: 0 if i % 2 == 0 else rep.get("testLoad"),
            m, decimals
        )
        cw["linearity_rows"] = lin_rows
        cw["eccentricity_rows"] = ecc_rows
        cw["repeatability_rows"] = rep_rows

        md = lane.get("md")
        if md:
            md = dict(md)
            dyn = cw.get("dynamicTests") or []
            articles = md.get("articles") or []
            normalized_articles = []
            for i, art in enumerate(articles):
                art = dict(art)
                art.setdefault("ferrous", {})
                art.setdefault("nonFerrous", {})
                art.setdefault("stainless", {})
                art.setdefault("extraTypes", [])
                linked = dyn[i] if i < len(dyn) else {}
                art["linked_name"] = linked.get("articleName", "")
                art["linked_number"] = linked.get("articleNumber", "")
                normalized_articles.append(art)
            md["articles"] = normalized_articles

        lanes_out.append({
            "laneNo": lane.get("laneNo"),
            "cw": cw,
            "md": md,
        })

    fr = dict(payload.get("finalReview") or {})
    fr.setdefault("technician", {})
    fr.setdefault("customer", {})

    return {
        "logo": WIPOTEC_LOGO_B64,
        "m": m,
        "test_kit": m.get("testKitRows") or [],
        "system_checklist": m.get("systemChecklist") or [],
        "additional_system_checklist": m.get("additionalSystemChecklist") or [],
        "optional_checklist": m.get("optionalChecklist") or [],
        "lanes": lanes_out,
        "fr": fr,
    }


@router.post("/cwcr/generate-pdf")
def generate_pdf(payload: dict = Body(...)):
    try:
        doc_no = payload.get("mainInfo", {}).get("documentNo", "")
        logger.info(f"Generate PDF requested for documentNo={doc_no!r}")

        ctx = build_pdf_context(payload)
        template = Template(HTML_TEMPLATE)
        rendered_html = template.render(**ctx)

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()

        m = payload.get("mainInfo", {}) or {}
        filename = "_".join([
            sanitize_filename_part(m.get("documentNo")),
            sanitize_filename_part(m.get("machineSerial")),
            sanitize_filename_part(m.get("companyName")),
        ]) + ".pdf"

        logger.info(f"PDF generated successfully for documentNo={doc_no!r} ({len(pdf_bytes)} bytes) -> {filename}")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"}
        )
