"""CW Commissioning & Qualification report (CWCQ): form config, PDF template and routes.

Built from the Excel template "WIPOTEC_Commissioning_CW_Report_V0.9.2.1.xlsx"
(sheets Cover Page, 1 General Information, 2 Installation Qualification,
3 Operational Qualification, 4 Instruments, 5 Related Documents, Data Backend).
All fixed wording lives here and the web form loads it via /cwcq-config, so the
form and the PDF always use the same item names.
"""
import base64
import logging
import re
import traceback
from pathlib import Path
from typing import Dict, List

import weasyprint
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from jinja2 import Template
from pydantic import BaseModel

from assets import LOGO_TOP_URI, LOGO_HEADER_URI, BASE_CSS, safe_filename_part, content_disposition

router = APIRouter()
logger = logging.getLogger("cwcq")
BASE_DIR = Path(__file__).resolve().parent
CWCQ_HTML_PATH = BASE_DIR / "commissioning.html"
MODEL_IMG_DIR = BASE_DIR / "commissioning_models"

# ------------------------------------------------------------
# Form configuration (single source of truth)
# ------------------------------------------------------------
# Machine models from the "Data Backend" sheet, in the same order. Each has a picture
# in commissioning_models/ (extracted from the Excel in-cell images).
MODELS = [
    "EC-Easy", "EC-E", "EC-E-SL", "EC-E-VA", "HC-M", "HC-M-VA", "HC-M-WD", "HC-M-MDi",
    "HC-M-WD-MDi", "HC-M-SL", "HC-M-SL-MDi", "HC-M-WD-SL", "HC-A", "HC-A-MI", "HC-A-VA",
    "HC-A-IS-WD", "HC-A-VI",
]
BUSINESS = ["Food & Pharma", "Mail & Logistic"]


def instrument_category(business: str) -> str:
    """OIML R 51-1 category for chapter 4: Mail & Logistic -> Y (catchweigher), otherwise X (checkweigher).
    Also accepts the older names "Food and Pharma (Checkweigher)" / "Mail & Logistic (Catchweigher)"."""
    return "Y" if (business or "").strip().lower().startswith("mail") else "X"


def instruments_title(business: str) -> str:
    b = (business or "").strip().lower()
    if b.startswith("food"):
        return "4. Checkweigher Instruments"
    if b.startswith("mail"):
        return "4. Catchweigher Instruments"
    return "4. Catchweighing / Checkweighing Instruments"
RESULTS = ["-", "Pass", "Failed", "N/A"]
SPEED_UNITS = ["m/sec", "m/min"]

INTRODUCTION = (
    "This Checkweigher Commissioning & Calibration Package helps manufacturers maintain strict "
    "quality standards, generates critical CCP documentation, serves as proof of due diligence, "
    "and verifies correct machine installation and operation."
)
ORIGINAL_NOTE = ("This document constitutes the original version. A certified electronic copy is "
                 "maintained in WIPOTEC Singapore.")

# Each checklist item: "text" or (text, hint). Hints are shown in the web form only
# (they come from the side notes in columns M/N of the Excel) and never printed.
IQ_SECTIONS = [
    {
        "id": "2.1", "title": "2.1 Order Processing",
        "objective": "To verify and record that the supplied WIPOTEC machine system, options, accessories, "
                     "and technical documentation strictly correspond to the customer purchase order and "
                     "WIPOTEC work order.",
        "methodology": [
            "Verify checkweigher model and configuration against WIPOTEC Order Confirmation.",
            "Inspect all delivered options, accessories, spare parts, and test kits.",
            "Confirm availability of Operating Manual, Electrical Schematics, and Layout Drawings.",
            "Verify Factory Calibration / FAT Certificates and compliance documents (e.g., CE, OIML, if applicable).",
        ],
        "acceptance": [
            "Machine specifications and serial number match the Order Confirmation.",
            "All ordered accessories, spare parts, and test weights are fully supplied.",
            "Complete technical manual and system drawings are provided on site.",
            "Valid Factory Certificates and required compliance documentation are present.",
        ],
        "items": [
            "Equipment has been supplied according to customers order/WIPOTEC WO",
            "EC Declaration of Conformity supplied",
            "System Manual supplied",
            "System Diagram supplied",
            "Spare Part Catalogue supplied",
            "Check Protocol supplied",
            "Accessories, consumables, spare parts on the Work order have been supplied",
        ],
    },
    {
        "id": "2.2", "title": "2.2 Equipment Condition",
        "objective": "To verify and document that the weight system, cables, and mechanical components are "
                     "installed without physical damage and maintain structural and sealing integrity.",
        "methodology": [
            "Perform a visual inspection of the checkweigher unit for any visible physical damage.",
            "Inspect all electrical cables, connectors, and cable gland assemblies for damage or improper installation.",
            "Check all seals and gaskets for wear, cracks, or damage that could compromise IP protection integrity.",
            "Check that all mechanical fasteners, screws, and fittings are present, securely tightened, and properly assembled.",
        ],
        "acceptance": [
            "No visible physical damage on the equipment frame, weigh cell, or conveyor belts.",
            "All cables, connectors, and cable glands are undamaged, securely routed, and tight.",
            "All seals and gaskets are intact, ensuring complete water and dust ingress protection (IP Rating).",
            "All screws, nuts, and mechanical fittings are fully present and correctly torque-tightened.",
        ],
        "items": [
            "No visible damage to the equipment",
            "No visible damage of cables",
            "Seals and gaskets inspected and found to be in good condition",
            "All screws and fittings are properly secured and in good mechanical condition",
            "Cable glands inspected and found to be properly installed and in good condition",
            "Weight cell lock is correctly positioned and secured",
        ],
    },
    {
        "id": "2.3", "title": "2.3 Customer Mechanical Installation & Environmental Conditions",
        "objective": "To verify and document that the checkweigher is correctly integrated with production lines, "
                     "free from mechanical interference, and operating in a suitable environment to ensure "
                     "weighing accuracy.",
        "methodology_groups": [
            ("Mechanical Integration & Line Alignment", [
                "Inspect all conveyor belts to ensure they are clean and free from contamination.",
                "Check that the weighing conveyor and weigh cell have complete clearance and no contact with "
                "external structures, guards, or neighboring conveyors.",
                "Verify smooth product transfer from the upstream (infeed) equipment onto the weight conveyor, "
                "and from the weight conveyor to the downstream (outfeed) equipment.",
                "Ensure the target product contacts only the conveyor belts during passage and does not collide "
                "with machine frames or sensors.",
                "Confirm that the control cabinet, HMI touch panel, maintenance units, reject bins, and printer "
                "are easily accessible for operation and servicing, with the rating plate clearly visible.",
            ]),
            ("Environmental Conditions", [
                "Verify that ambient room temperature and relative humidity satisfy WIPOTEC operating and storage specifications.",
                "Inspect the installation area to ensure the checkweigher is free from excessive external vibration, shock, or air drafts.",
            ]),
        ],
        "acceptance": [
            "No physical contact or external mechanical interference exists on the weigh cell or weighing conveyor.",
            "Product transfer across infeed, weighing, and outfeed conveyors is smooth without jammed products or tumbling.",
            "Target products touch only the active conveyor belt surface during weighing.",
            "HMI panel, control cabinet, reject collection bins, and maintenance points are fully accessible.",
            "Facility ambient temperature, humidity, and IP protection level strictly meet machine operating guidelines.",
            "The checkweigher mounting location is stable and isolated from severe floor vibration or structural shocks.",
        ],
        "items": [
            "No visible signs of contamination on the belt surface",
            "No contact or interference between conveyors",
            "No physical contact or interference with the Weight cell or associated components",
            "No product transfer issues at the checkweigher infeed and outfeed",
            "All components, e.g. cabinet, HMI, bins and switches are easily accessible.",
            "Facility environmental conditions are in accordance with requirements submitted to WIPOTEC.",
            "Facility conditions meet requirements submitted to WIPOTEC.",
        ],
    },
    {
        "id": "2.4", "title": "2.4 Customer Electrical Installation",
        "items": [
            "System earthing and unit grounding verified.",
            "Checkweigher cables are correctly routed and secured. (L,N and G)",
            "Connection between the control cabinet and Weight cell is properly installed and secured.",
        ],
    },
]

OQ_SECTIONS = [
    {
        "id": "3.1", "title": "3.1 Conveyor, Reject Mechanism & Additional Functions",
        "items": [
            ("Belt runs smoothly and remains centered on the rollers.", "When running, belt stays centered"),
            ("Photo eye sensor or edge length sensor function properly.", "Measures the product length correctly"),
            ("No interference or contact between the rejecter and surrounding parts.",
             "e.g. pusher does not contact the conveyor when mounted or activated"),
            ("Sorting function and related devices (reject bin and sensor)",
             "e.g. pusher operates correctly into the reject bin area and the sensor works"),
            ("Conveyors stop upon activation of the safety circuit.", "Optional"),
            ("Upon safety circuit activation, the air supply is shut off.", "Optional"),
        ],
    },
    {
        "id": "3.2", "title": "3.2 Additional Functions (Optional)",
        "hint": "See options in the WO",
        "items": [
            ("Collect statistic data package via USB",
             "e.g. options such as USB, Ethernet, RS232, printer for export - see WO"),
            ("Send statistic data package via serial interface / Ethernet",
             "e.g. transmitted data is consistent with the configured settings"),
            "Send single weight values via Ethernet",
            ("Emergency-Stop", "e.g. push-button, drives, pneumatic, 2-channel emergency off control unit"),
            "Product flow control",
            "Verification of rejection via light barrier",
            "Air pressure check for pneumatics",
            ("Sorting lamp", "e.g. 1 colour, 3 colour, signal horn"),
            "Guide rails",
            "Factory certificate for Weigh Cells",
            ("Lockable box for sorted / rejected products",
             "e.g. check correct material: robust plastic or stainless steel"),
            "Recognition of consecutive errors",
            "Extension of article storage",
            "Filling head statistics",
            ("User administration according to CFR21 PART 11", "e.g. user-password login, RFID reader"),
        ],
    },
]
OQ_OBJECTIVE = ("Demonstrate that basic checkweigher functions perform appropriately. "
                "Only use certified tachometer with deviation <1%.")

TEST_KIT_DEFAULT = ["Weight kit 200mg–500g", "Weight kit 1kg", "Weight kit 2kg", "Tachometer", "Multimeter"]
CAL_REPORT_SLOTS = 5


def _items(section):
    """Normalise items to [{name, hint}]."""
    out = []
    for it in section["items"]:
        name, hint = (it if isinstance(it, tuple) else (it, ""))
        out.append({"name": name, "hint": hint})
    return out


# ------------------------------------------------------------
# Request model
# ------------------------------------------------------------
class Party(BaseModel):
    name: str = ""
    address: str = ""
    country: str = ""
    zip_code: str = ""
    poc_name: str = ""
    poc_phone: str = ""
    poc_email: str = ""


class WeightCell(BaseModel):
    cell_type: str = ""
    cell_id: str = ""
    pd: str = ""
    serial: str = ""
    max: str = ""
    e: str = ""
    d: str = ""
    dead_load: str = ""


class Lane(BaseModel):
    min_throughput: str = ""
    max_throughput: str = ""
    speed_unit: str = "m/sec"
    min_speed_display: str = ""
    min_speed_measured: str = ""
    max_speed_display: str = ""
    max_speed_measured: str = ""


class TestKitRow(BaseModel):
    equipment: str = ""
    serial: str = ""
    cert: str = ""
    cal_date: str = ""
    due_date: str = ""


class CWCQData(BaseModel):
    doc_no: str = ""
    model: str = ""
    model_image: str = ""   # data URL, only when the model is "Other" and a picture was attached
    model_number: str = ""
    serial_no: str = ""
    customer: Party = Party()
    end_user: Party = Party()
    business: str = ""
    software_version: str = ""
    protection_class: str = ""
    manufacturing_year: str = ""
    location: str = ""
    asset_number: str = ""
    additional_info: str = ""
    # checks[section_id][item_name] = {"result": "...", "remark": "..."}
    checks: Dict[str, Dict[str, Dict[str, str]]] = {}
    weight_cells: List[WeightCell] = []
    voltage_plate: str = ""
    voltage_measured: str = ""
    voltage_remark: str = ""
    frequency_plate: str = ""
    frequency_measured: str = ""
    frequency_remark: str = ""
    iq_comments: str = ""
    lanes: List[Lane] = []
    instruments_remarks: str = ""
    cal_reports: List[str] = []
    test_kit: List[TestKitRow] = []
    customer_sign_name: str = ""
    customer_sign_position: str = ""
    customer_sign_phone: str = ""
    customer_sign_email: str = ""
    customer_sign_date: str = ""
    customer_signature: str = ""
    technician_name: str = ""
    technician_date: str = ""
    technician_signature: str = ""
    service_comments: str = ""


# ------------------------------------------------------------
# Calculations
# ------------------------------------------------------------
def _num(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def speed_deviation(display, measured):
    """Deviation of the measured conveyor speed from the displayed one, in %.

    Same formula as the Excel (=((measured-display)/display)*100). PASS when |dev| < 1 %.
    Returns (text, css_class).
    """
    d, m = _num(display), _num(measured)
    if d is None or m is None:
        return "—", "na-text"
    if d == 0:
        return "—", "na-text"
    dev = (m - d) / d * 100
    ok = abs(dev) < 1
    return f"{dev:+.2f} % ({'PASS' if ok else 'FAIL'})", ("pass-text" if ok else "fail-text")


def _cls(v: str) -> str:
    v = (v or "").strip().lower()
    if v == "pass":
        return "pass-text"
    if v in ("failed", "fail"):
        return "fail-text"
    return "na-text"


def _model_image_path(model: str):
    if model not in MODELS:
        return None
    for p in MODEL_IMG_DIR.glob(re.sub(r"[^A-Za-z0-9-]", "_", model) + ".*"):
        return p
    return None


_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+$")


def _cover_image_uri(data) -> str:
    """Picture for the cover: an attached picture ("Other" model) wins, else the stock model picture."""
    img = (data.model_image or "").strip()
    if img and _DATA_URL_RE.match(img):
        return img
    return _model_image_uri(data.model)


def _model_image_uri(model: str) -> str:
    p = _model_image_path(model)
    if not p:
        return ""
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


# ------------------------------------------------------------
# PDF template
# ------------------------------------------------------------
CWCQ_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @page {
    size: A4; margin: 22mm 10mm 14mm 10mm;
    @top-left { content: "Document No.: {{ doc_css }}"; font-family: Arial, sans-serif; font-size: 8pt; color: #333; vertical-align: bottom; padding-bottom: 5px; }
    @top-right { content: url('{{ logo_top }}'); vertical-align: bottom; padding-bottom: 5px; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: Arial, sans-serif; font-size: 8pt; color: #555; }
    @bottom-left { content: "WIPOTEC Checkweigher Commissioning & Qualification"; font-family: Arial, sans-serif; font-size: 7pt; color: #777; }
  }
  @page cover { margin: 14mm 12mm 12mm 12mm; @top-left { content: ""; } @top-right { content: ""; } @bottom-left { content: ""; } @bottom-right { content: ""; } }
  {{ base_css }}
  .cover { page: cover; page-break-after: always; break-after: page; height: 268mm; position: relative; }
  .cover-logo { text-align: right; }
  .cover-logo img { width: 190px; }
  .cover-title { margin-top: 28mm; font-size: 22pt; font-weight: bold; color: #1a1a1a; }
  .cover-title .slash { font-size: 22pt; }
  .cover-sub { font-size: 11pt; color: #007777; margin-top: 2mm; }
  .cover-info { margin-top: 10mm; width: 60%; border-collapse: collapse; }
  .cover-info td { padding: 4px 6px; font-size: 10pt; border-bottom: 1px solid #c2d6d6; }
  .cover-info td.k { width: 38%; font-weight: bold; color: #333; }
  .cover-img { margin-top: 10mm; text-align: center; }
  .cover-img img { max-width: 150mm; max-height: 120mm; }
  .cover-foot { position: absolute; bottom: 0; left: 0; right: 0; border-top: 2px solid #009999; padding-top: 3mm; }
  .cover-foot table { width: 100%; border-collapse: collapse; }
  .cover-foot td { width: 50%; vertical-align: top; font-size: 7.5pt; line-height: 1.35; color: #333; }
  .cover-foot b { font-size: 8.5pt; }
  .chapter { page-break-before: always; break-before: page; }
  .chapter-title { font-size: 12pt; font-weight: bold; color: #000; margin: 0 0 6px; }
  .sub-head { font-weight: bold; color: #007777; font-size: 8.5pt; margin: 8px 0 3px; page-break-after: avoid; break-after: avoid; }
  .text-block { font-size: 7.5pt; margin: 2px 0 4px; }
  .text-block ul { margin: 2px 0 2px 14px; padding: 0; }
  .text-block li { margin: 0 0 1px; }
  .desc-table td { vertical-align: top; }
  .desc-table td.k { width: 18%; font-weight: bold; background: #f2f8f8; color: #333; }
  .res-col { width: 60px; text-align: center; font-weight: bold; }
  .rmk-col { width: 32%; }
  .two-col { width: 100%; border-collapse: collapse; }
  .two-col > tbody > tr > td { width: 50%; vertical-align: top; padding: 0 2px; }
  .oiml td, .oiml th { text-align: center; }
  .oiml td.l { text-align: left; }
  .note { font-size: 7pt; color: #444; margin: 2px 0 6px; }
  .sig-box img { max-height: 50px; max-width: 90%; }
  .sig-meta { width: 100%; border-collapse: collapse; margin-top: 4px; }
  .sig-meta td { font-size: 7.5pt; padding: 1px 4px; text-align: left; border: none; }
  .sig-meta td.k { width: 30%; font-weight: bold; color: #333; }
  .orig { font-size: 7pt; color: #666; margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px; }
</style></head>
<body>

{# ======================= COVER ======================= #}
<div class="cover">
  <div class="cover-logo"><img src="{{ logo_header }}" alt="WIPOTEC"></div>
  <div class="cover-title"><span class="slash">/</span> Commissioning and Qualification Report</div>
  <div class="cover-sub">Checkweigher</div>
  <table class="cover-info">
    <tr><td class="k">Model</td><td>{{ d.model or '—' }}</td></tr>
    <tr><td class="k">Model number</td><td>{{ d.model_number or '—' }}</td></tr>
    <tr><td class="k">Serial number</td><td><strong>{{ d.serial_no or '—' }}</strong></td></tr>
    <tr><td class="k">Document No.</td><td>{{ d.doc_no or '—' }}</td></tr>
  </table>
  {% if model_img %}<div class="cover-img"><img src="{{ model_img }}" alt="{{ d.model }}"></div>{% endif %}
  <div class="cover-foot"><table><tr>
    <td><b>WIPOTEC GmbH</b><br>Adam-Hoffmann-Straße 26<br>67657 Kaiserslautern<br>Phone: +49 631 34146-0<br>info@wipotec.com<br>www.wipotec.com</td>
    <td><b>WIPOTEC Singapore Pte Ltd.</b><br>German Centre for Industry &amp; Trade 25<br>International Business Park<br>#03-29 German Centre 609916 Singapore<br>T +65 690 80 358 / F +65 690 80 359<br>service.sea@wipotec.com</td>
  </tr></table></div>
</div>

{# ======================= 1. GENERAL ======================= #}
<div class="chapter-title"><span class="slash">/</span> 1. General Information</div>
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Introduction</div>
  <div class="text-block">{{ introduction }}</div>
</div>

{% macro party_table(title, p) %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ title }}</div>
  <table class="data-table">
    <tr><td class="label-col">Customer Name</td><td class="val-col"><strong>{{ p.name }}</strong></td></tr>
    <tr><td class="label-col">Address</td><td class="val-col">{{ p.address }}</td></tr>
    <tr><td class="label-col">Country</td><td class="val-col">{{ p.country }}</td></tr>
    <tr><td class="label-col">Zip Code</td><td class="val-col">{{ p.zip_code }}</td></tr>
    <tr><td class="label-col">Point of Contact</td><td class="val-col">{{ p.poc_name }}</td></tr>
    <tr><td class="label-col">Phone</td><td class="val-col">{{ p.poc_phone }}</td></tr>
    <tr><td class="label-col">Email</td><td class="val-col">{{ p.poc_email }}</td></tr>
  </table>
</div>
{% endmacro %}
<table class="two-col"><tr>
  <td>{{ party_table('Customer Information', d.customer) }}</td>
  <td>{{ party_table('End User Information', d.end_user) }}</td>
</tr></table>

<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Machine Info</div>
  <table class="data-table">
    <tr><td class="label-col">Business</td><td class="val-col" colspan="3">{{ d.business }}</td></tr>
    <tr><td class="label-col">Machine Model / Type</td><td class="val-col">{{ d.model }}</td>
        <td class="label-col">Model Number</td><td class="val-col">{{ d.model_number }}</td></tr>
    <tr><td class="label-col">Machine Serial Number</td><td class="val-col"><strong>{{ d.serial_no }}</strong></td>
        <td class="label-col">Software Version</td><td class="val-col">{{ d.software_version }}</td></tr>
    <tr><td class="label-col">Protection Class</td><td class="val-col">{{ d.protection_class }}</td>
        <td class="label-col">Manufacturing Year</td><td class="val-col">{{ d.manufacturing_year }}</td></tr>
    <tr><td class="label-col">Location</td><td class="val-col">{{ d.location }}</td>
        <td class="label-col">Customer Asset Number</td><td class="val-col">{{ d.asset_number }}</td></tr>
  </table>
</div>
{% if d.additional_info %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Additional Information</div>
  <div class="text-block">{{ d.additional_info }}</div>
</div>
{% endif %}
<div class="orig">{{ original_note }}</div>

{# ======================= 2. IQ ======================= #}
{% macro checklist(sec_id, items) %}
<table class="checklist-table">
  <tr><th>Checklist</th><th class="res-col">Result</th><th class="rmk-col">Remark</th></tr>
  {% for it in items %}{% set r = results[sec_id][it.name] %}
  <tr><td>{{ it.name }}</td><td class="res-col {{ cls(r.result) }}">{{ r.result }}</td><td>{{ r.remark }}</td></tr>
  {% endfor %}
</table>
{% endmacro %}

{% macro bullets(lines) %}<ul>{% for l in lines %}<li>{{ l }}</li>{% endfor %}</ul>{% endmacro %}

<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 2. Installation Qualification</div>
{% for s in iq %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ s.title }}</div>
  {% if s.objective %}
  <table class="data-table desc-table">
    <tr><td class="k">Objective</td><td>{{ s.objective }}</td></tr>
    <tr><td class="k">Methodology / Test Procedure</td><td class="text-block">
      {% if s.methodology %}{{ bullets(s.methodology) }}{% endif %}
      {% for g, lines in s.methodology_groups or [] %}<strong>{{ g }}:</strong>{{ bullets(lines) }}{% endfor %}
    </td></tr>
    <tr><td class="k">Acceptance Criteria</td><td class="text-block">{{ bullets(s.acceptance) }}</td></tr>
  </table>
  {% endif %}
  {% if s.id == '2.4' %}
  <table class="checklist-table">
    <tr><th>Name Plate Information</th><th>Plate Info</th><th>Measured Info</th><th>Remark</th></tr>
    <tr><td>Voltage (Vac)</td><td>{{ d.voltage_plate }}</td><td>{{ d.voltage_measured }}</td><td>{{ d.voltage_remark }}</td></tr>
    <tr><td>Frequency (Hz)</td><td>{{ d.frequency_plate }}</td><td>{{ d.frequency_measured }}</td><td>{{ d.frequency_remark }}</td></tr>
  </table>
  {% endif %}
  {{ checklist(s.id, s.items_n) }}
</div>
{% if s.id == '2.2' %}
{% for wc in d.weight_cells %}
<div class="section-block">
  <div class="sub-head">Weight Cell No. {{ loop.index }} Information</div>
  <table class="data-table" style="table-layout: fixed;">
    <tr><td class="label-col">Weight Cell Type</td><td class="val-col">{{ wc.cell_type }}</td><td class="label-col">Max</td><td class="val-col">{{ wc.max }}</td></tr>
    <tr><td class="label-col">ID</td><td class="val-col">{{ wc.cell_id }}</td><td class="label-col">e</td><td class="val-col">{{ wc.e }}</td></tr>
    <tr><td class="label-col">PD</td><td class="val-col">{{ wc.pd }}</td><td class="label-col">d</td><td class="val-col">{{ wc.d }}</td></tr>
    <tr><td class="label-col">Serial Number</td><td class="val-col">{{ wc.serial }}</td><td class="label-col">Dead Load</td><td class="val-col">{{ wc.dead_load }}</td></tr>
  </table>
</div>
{% endfor %}
{% endif %}
{% endfor %}
{% if d.iq_comments %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Additional Comments</div>
  <div class="text-block">{{ d.iq_comments }}</div>
</div>
{% endif %}
<div class="orig">{{ original_note }}</div>
</div>

{# ======================= 3. OQ ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 3. Operational Qualification</div>
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ oq[0].title }}</div>
  <div class="text-block"><strong>Objective:</strong> {{ oq_objective }}</div>
  {% for ln in lanes %}
  <div class="sub-head">Conveyor Lane No. {{ loop.index }}</div>
  <table class="checklist-table">
    <tr><th>Parameter</th><th>Display Value</th><th>Units</th><th>Parameter</th><th>Display Value</th><th>Measured Value</th><th>Deviation &lt;1%</th></tr>
    <tr><td>Min. Throughput</td><td>{{ ln.l.min_throughput }}</td><td>Pcs/min</td><td>Min. Conveyor speed</td>
        <td>{{ ln.l.min_speed_display }} {{ ln.l.speed_unit }}</td><td>{{ ln.l.min_speed_measured }} {{ ln.l.speed_unit }}</td><td class="{{ ln.min_cls }}">{{ ln.min_dev }}</td></tr>
    <tr><td>Max. Throughput</td><td>{{ ln.l.max_throughput }}</td><td>Pcs/min</td><td>Max. Conveyor speed</td>
        <td>{{ ln.l.max_speed_display }} {{ ln.l.speed_unit }}</td><td>{{ ln.l.max_speed_measured }} {{ ln.l.speed_unit }}</td><td class="{{ ln.max_cls }}">{{ ln.max_dev }}</td></tr>
  </table>
  {% endfor %}
  {{ checklist(oq[0].id, oq[0].items_n) }}
</div>
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ oq[1].title }}</div>
  {{ checklist(oq[1].id, oq[1].items_n) }}
</div>
<div class="orig">{{ original_note }}</div>
</div>

{# ======================= 4. INSTRUMENTS ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> {{ instr_title }}</div>
{% if cat == "Y" %}
<div class="section-header"><span class="slash" style="color:#fff;">/</span> 4.1 OIML R 51-1 (Edition 2006) — Category Y Instruments</div>

<div class="section-block">
  <div class="sub-head">4.1.1 Verification scale interval (OIML R 51-1, clause 2.2.1 and Table 1)</div>
  <div class="text-block">The verification scale interval (e) and the number of verification scale intervals (n = Max / e) are given per accuracy class in Table 1.</div>
  <table class="checklist-table oiml">
    <tr><th rowspan="2">Accuracy class</th><th rowspan="2">Verification scale interval, e</th><th colspan="2">Number of verification scale intervals, n = Max / e</th></tr>
    <tr><th>Minimum</th><th>Maximum</th></tr>
    <tr><td>Y(I)</td><td>0.001 g ≤ e *</td><td>50 000</td><td>–</td></tr>
    <tr><td rowspan="2">Y(II)</td><td>0.001 g ≤ e ≤ 0.05 g</td><td>100</td><td>100 000</td></tr>
    <tr><td>0.1 g ≤ e</td><td>5 000</td><td>100 000</td></tr>
    <tr><td rowspan="2">Y(a)</td><td>0.1 g ≤ e ≤ 2 g</td><td>100</td><td>10 000</td></tr>
    <tr><td>5 g ≤ e</td><td>500</td><td>10 000</td></tr>
    <tr><td>Y(b)</td><td>5 g ≤ e</td><td>100</td><td>1 000</td></tr>
  </table>
  <div class="note">* It is normally not feasible to test and verify an instrument where e &lt; 1 mg, due to the uncertainty of the test loads.<br>
  Multiple range instruments: e1 &lt; e2 &lt; … &lt; er (Min, n and Max indexed accordingly); each range is treated as an instrument with one range.</div>
</div>

<div class="section-block">
  <div class="sub-head">4.1.2 Maximum permissible errors — automatic operation (OIML R 51-1, clause 2.5.1.2 and Table 5)</div>
  <div class="text-block">The maximum permissible error for any load m with Min ≤ m ≤ Max in automatic operation shall be as specified in Table 5.</div>
  <table class="checklist-table oiml">
    <tr><th colspan="4">Load, m, expressed in verification scale intervals, e</th><th colspan="2">Maximum permissible error *</th></tr>
    <tr><th>Y(I)</th><th>Y(II)</th><th>Y(a)</th><th>Y(b)</th><th>Initial verification</th><th>In-service inspection</th></tr>
    <tr><td>0 &lt; m ≤ 50 000</td><td>0 &lt; m ≤ 5 000</td><td>0 &lt; m ≤ 500</td><td>0 &lt; m ≤ 50</td><td>±1 e</td><td>±1.5 e</td></tr>
    <tr><td>50 000 &lt; m ≤ 200 000</td><td>5 000 &lt; m ≤ 20 000</td><td>500 &lt; m ≤ 2 000</td><td>50 &lt; m ≤ 200</td><td>±1.5 e</td><td>±2.5 e</td></tr>
    <tr><td>200 000 &lt; m</td><td>20 000 &lt; m ≤ 100 000</td><td>2 000 &lt; m ≤ 10 000</td><td>200 &lt; m ≤ 1 000</td><td>±2 e</td><td>±3.5 e</td></tr>
  </table>
  <div class="note">* Applies to instruments with a device displaying the digital indication with d ≤ 0.2 e (see A.3.9.2.1); without such a device, the procedure in A.3.9.2.2 applies.<br>
  If the net weight is calculated by subtracting two individual weighings, the MPEs apply to the individual weighings if they are printed or recorded separately, or to the net weight if only the net weight is printed.</div>
</div>

<div class="section-block">
  <div class="sub-head">4.1.3 Number of test weighings (OIML R 51-1, clause 6.1.2 and Table 7)</div>
  <div class="text-block">Minimum number of consecutive test weighings used to determine the individual errors for Category Y instruments:</div>
  <table class="checklist-table oiml">
    <tr><th>Load, m</th><th>Number of test weighings</th></tr>
    <tr><td class="l">Any load</td><td>Minimum of 10</td></tr>
  </table>
  <div class="note">The number of test weighings shall be at least ten unless a special test procedure is specified in the type approval certificate.<br>
  Source: OIML R 51-1 Edition 2006 (E) — Automatic catchweighing instruments, Part 1: Metrological and technical requirements — Tests. Category Y values only.</div>
</div>
{% else %}
<div class="section-header"><span class="slash" style="color:#fff;">/</span> 4.1 OIML R 51-1 (Edition 2006) — Category X Instruments</div>

<div class="section-block">
  <div class="sub-head">4.1.1 Verification scale interval (OIML R 51-1, clause 2.2.1 and Table 1)</div>
  <div class="text-block">The verification scale interval (e) and the number of verification scale intervals (n = Max / e) are given per accuracy class in Table 1.</div>
  <table class="checklist-table oiml">
    <tr><th rowspan="2">Accuracy class</th><th rowspan="2">Verification scale interval, e</th><th colspan="2">Number of verification scale intervals, n = Max / e</th></tr>
    <tr><th>Minimum</th><th>Maximum</th></tr>
    <tr><td>XI</td><td>0.001 g ≤ e *</td><td>50 000</td><td>–</td></tr>
    <tr><td rowspan="2">XII</td><td>0.001 g ≤ e ≤ 0.05 g</td><td>100</td><td>100 000</td></tr>
    <tr><td>0.1 g ≤ e</td><td>5 000</td><td>100 000</td></tr>
    <tr><td rowspan="2">XIII</td><td>0.1 g ≤ e ≤ 2 g</td><td>100</td><td>10 000</td></tr>
    <tr><td>5 g ≤ e</td><td>500</td><td>10 000</td></tr>
    <tr><td>XIIII</td><td>5 g ≤ e</td><td>100</td><td>1 000</td></tr>
  </table>
  <div class="note">* It is normally not feasible to test and verify an instrument where e &lt; 1 mg, due to the uncertainty of the test loads.<br>
  Multiple range instruments: e1 &lt; e2 &lt; … &lt; er (Min, n and Max indexed accordingly); each range is treated as an instrument with one range.</div>
</div>

<div class="section-block">
  <div class="sub-head">4.1.2 Maximum permissible errors — automatic operation (OIML R 51-1, clause 2.5.1.1, Tables 3 and 4)</div>
  <div class="text-block">For consecutive weighings of a net load m with Min ≤ m ≤ Max: the mean (systematic) error shall not exceed Table 3, and the standard deviation of the error (random error) shall not exceed Table 4 multiplied by the class designation factor (x).</div>
  <table class="checklist-table oiml">
    <tr><th colspan="4">Net load, m, expressed in verification scale intervals, e</th><th colspan="2">Maximum permissible mean error</th></tr>
    <tr><th>XI</th><th>XII</th><th>XIII</th><th>XIIII</th><th>Initial verification</th><th>In-service inspection</th></tr>
    <tr><td>0 &lt; m ≤ 50 000</td><td>0 &lt; m ≤ 5 000</td><td>0 &lt; m ≤ 500</td><td>0 &lt; m ≤ 50</td><td>±0.5 e</td><td>±1 e</td></tr>
    <tr><td>50 000 &lt; m ≤ 200 000</td><td>5 000 &lt; m ≤ 20 000</td><td>500 &lt; m ≤ 2 000</td><td>50 &lt; m ≤ 200</td><td>±1 e</td><td>±2 e</td></tr>
    <tr><td>200 000 &lt; m</td><td>20 000 &lt; m ≤ 100 000</td><td>2 000 &lt; m ≤ 10 000</td><td>200 &lt; m ≤ 1 000</td><td>±1.5 e</td><td>±3 e</td></tr>
  </table>
  <table class="checklist-table oiml" style="margin-top:4px;">
    <tr><th rowspan="2">Value of the mass of the net load, m (g)</th><th colspan="2">Max. permissible standard deviation (% of m or in g), (x) = 1</th></tr>
    <tr><th>Initial verification</th><th>In-service inspection</th></tr>
    {% for a, b, c in sd_rows %}<tr><td class="l">{{ a }}</td><td>{{ b }}</td><td>{{ c }}</td></tr>{% endfor %}
  </table>
  <div class="note">Class designation factor (x): Classes XI and XII — (x) &lt; 1; Class XIII — (x) ≤ 1; Class XIIII — (x) &gt; 1.</div>
</div>

<div class="section-block">
  <div class="sub-head">4.1.3 Number of test weighings (OIML R 51-1, clause 6.1.2 and Table 7)</div>
  <div class="text-block">Minimum number of consecutive test weighings used to determine the mean error and the standard deviation of the error for Category X instruments:</div>
  <table class="checklist-table oiml">
    <tr><th>Load, m</th><th>Number of test weighings</th></tr>
    <tr><td class="l">m ≤ 1 kg</td><td>60</td></tr>
    <tr><td class="l">1 kg &lt; m ≤ 10 kg</td><td>30</td></tr>
    <tr><td class="l">10 kg &lt; m ≤ 20 kg</td><td>20</td></tr>
    <tr><td class="l">20 kg &lt; m</td><td>10</td></tr>
  </table>
  <div class="note">Source: OIML R 51-1 Edition 2006 (E) — Automatic catchweighing instruments, Part 1: Metrological and technical requirements — Tests. Category X values only.</div>
</div>
{% endif %}
{% if d.instruments_remarks %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Remarks</div>
  <div class="text-block">{{ d.instruments_remarks }}</div>
</div>
{% endif %}
<div class="orig">{{ original_note }}</div>
</div>

{# ======================= 5. RELATED DOCUMENTS ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 5. Related Documents &amp; Sign</div>
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> 5.1 Calibration Report Number</div>
  <table class="data-table">
    {% for r in cal_reports %}<tr><td class="label-col">Checkweigher / Weight Scale No.{{ loop.index }}</td><td class="val-col">{{ r }}</td></tr>{% endfor %}
  </table>
</div>
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> WIPOTEC Test Kit Information</div>
  <table class="checklist-table">
    <tr><th>Equipment Type</th><th>Serial Number</th><th>Certificate No.</th><th>Calibration Date</th><th>Due Date</th></tr>
    {% for t in d.test_kit %}<tr><td>{{ t.equipment }}</td><td>{{ t.serial }}</td><td>{{ t.cert }}</td><td>{{ t.cal_date }}</td><td>{{ t.due_date }}</td></tr>{% endfor %}
  </table>
</div>
<div class="section-block">
  <table class="signature-table"><tr>
    <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Customer Signature</div>
      {% if d.customer_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ d.customer_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
      <table class="sig-meta">
        <tr><td class="k">Name :</td><td>{{ d.customer_sign_name }}</td></tr>
        <tr><td class="k">Position :</td><td>{{ d.customer_sign_position }}</td></tr>
        <tr><td class="k">Phone :</td><td>{{ d.customer_sign_phone }}</td></tr>
        <tr><td class="k">Email :</td><td>{{ d.customer_sign_email }}</td></tr>
        <tr><td class="k">Date :</td><td>{{ d.customer_sign_date }}</td></tr>
      </table></div></td>
    <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Service Technician Signature</div>
      {% if d.technician_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ d.technician_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
      <table class="sig-meta">
        <tr><td class="k">Name :</td><td>{{ d.technician_name }}</td></tr>
        <tr><td class="k">Date :</td><td>{{ d.technician_date }}</td></tr>
      </table></div></td>
  </tr></table>
</div>
{% if d.service_comments %}
<div class="section-block">
  <div class="section-header"><span class="slash" style="color:#fff;">/</span> Additional Service Comments</div>
  <div class="text-block">{{ d.service_comments }}</div>
</div>
{% endif %}
<div class="orig">{{ original_note }}</div>
</div>
</body></html>
"""

SD_ROWS = [
    ("m ≤ 50", "0.48 %", "0.6 %"), ("50 < m ≤ 100", "0.24 g", "0.3 g"),
    ("100 < m ≤ 200", "0.24 %", "0.3 %"), ("200 < m ≤ 300", "0.48 g", "0.6 g"),
    ("300 < m ≤ 500", "0.16 %", "0.2 %"), ("500 < m ≤ 1 000", "0.8 g", "1.0 g"),
    ("1 000 < m ≤ 10 000", "0.08 %", "0.1 %"), ("10 000 < m ≤ 15 000", "8 g", "10 g"),
    ("15 000 < m", "0.053 %", "0.067 %"),
]


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@router.get("/commissioning.html")
def serve_cwcq_html():
    return FileResponse(CWCQ_HTML_PATH)


@router.get("/cwcq-config")
def cwcq_config():
    def sec(s):
        return {"id": s["id"], "title": s["title"], "hint": s.get("hint", ""), "items": _items(s)}
    return {
        "models": MODELS,
        "business": BUSINESS,
        "results": RESULTS,
        "speed_units": SPEED_UNITS,
        "iq": [sec(s) for s in IQ_SECTIONS],
        "oq": [sec(s) for s in OQ_SECTIONS],
        "test_kit_default": TEST_KIT_DEFAULT,
        "cal_report_slots": CAL_REPORT_SLOTS,
    }


@router.get("/cwcq-logo")
def cwcq_logo():
    """Header logo for the web form, served from the shared asset (no extra copy in the HTML)."""
    return Response(content=base64.b64decode(LOGO_HEADER_URI.split(",", 1)[1]), media_type="image/png",
                    headers={"Cache-Control": "max-age=86400"})


@router.get("/cwcq-model/{model}")
def cwcq_model_image(model: str):
    p = _model_image_path(model)
    if not p:
        raise HTTPException(status_code=404, detail="Unknown model")
    return FileResponse(p)


@router.post("/generate-cwcq-pdf")
def generate_cwcq_pdf(data: CWCQData):
    try:
        logger.info(f"Generate CWCQ PDF requested for doc_no={data.doc_no!r}")
        pdf = _build_cwcq_pdf(data)
        logger.info(f"CWCQ PDF generated successfully for doc_no={data.doc_no!r} ({len(pdf)} bytes)")
    except Exception as e:
        logger.error(f"CWCQ PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500,
                            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"})
    name = f"CWCQ_Report_{safe_filename_part(data.doc_no)}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(name)})


def _build_cwcq_pdf(data: CWCQData) -> bytes:
    d = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    def norm_sections(sections):
        out = []
        for s in sections:
            s2 = dict(s)
            s2["items_n"] = _items(s)
            out.append(s2)
        return out

    iq, oq = norm_sections(IQ_SECTIONS), norm_sections(OQ_SECTIONS)
    results = {}
    for s in iq + oq:
        sent = data.checks.get(s["id"], {})
        results[s["id"]] = {
            it["name"]: {"result": (sent.get(it["name"], {}).get("result") or "-"),
                         "remark": sent.get(it["name"], {}).get("remark", "")}
            for it in s["items_n"]
        }

    lanes = []
    for ln in (data.lanes or [Lane()]):
        min_dev, min_cls = speed_deviation(ln.min_speed_display, ln.min_speed_measured)
        max_dev, max_cls = speed_deviation(ln.max_speed_display, ln.max_speed_measured)
        lanes.append({"l": ln.model_dump() if hasattr(ln, "model_dump") else ln.dict(),
                      "min_dev": min_dev, "min_cls": min_cls, "max_dev": max_dev, "max_cls": max_cls})

    cal_reports = (list(data.cal_reports) + [""] * CAL_REPORT_SLOTS)[:CAL_REPORT_SLOTS]
    if not d["weight_cells"]:
        d["weight_cells"] = [WeightCell().model_dump()]
    if not d["test_kit"]:
        d["test_kit"] = [{"equipment": e, "serial": "", "cert": "", "cal_date": "", "due_date": ""}
                         for e in TEST_KIT_DEFAULT]

    doc_css = data.doc_no.replace("\\", "").replace('"', "").replace("\n", " ")
    html = Template(CWCQ_TEMPLATE).render(
        d=d, iq=iq, oq=oq, results=results, lanes=lanes, cal_reports=cal_reports,
        sd_rows=SD_ROWS, cls=_cls, introduction=INTRODUCTION, original_note=ORIGINAL_NOTE,
        oq_objective=OQ_OBJECTIVE, doc_css=doc_css, base_css=BASE_CSS,
        logo_top=LOGO_TOP_URI, logo_header=LOGO_HEADER_URI,
        model_img=_cover_image_uri(data),
        cat=instrument_category(data.business), instr_title=instruments_title(data.business),
    )
    return weasyprint.HTML(string=html).write_pdf()
