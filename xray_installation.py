"""X-Ray Installation & Qualification report (XRIQ): form config, PDF template and routes.

WIPOTEC installation report for X-ray inspection systems: customer and system
information, installation checks, operation checks (safety circuit, machine
functions, product set-up), training and sign-off. All fixed wording lives here
and the web form loads it via /xriq-config, so the form and PDF always match.
"""
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
logger = logging.getLogger("xriq")
XRIQ_HTML_PATH = Path(__file__).resolve().parent / "xray_installation.html"

# ------------------------------------------------------------
# Form configuration (single source of truth)
# ------------------------------------------------------------
RESULTS = ["-", "Pass", "Failed", "N/A"]
YESNO = ["-", "Yes", "No", "N/A"]
QUALIFICATION_PURPOSES = ["Initial Installation", "Relocation", "Re-qualification", "Other"]
CONNECTIVITY = ["None", "Ethernet", "Profinet", "EtherNet/IP", "OPC UA", "Other"]
MAINS_RANGES = [(208, 250, "208 – 250 V AC / 50-60 Hz"), (110, 120, "110 – 120 V AC / 50-60 Hz")]
FRR_LIMIT = 0.05  # %

TEXT = {
    "intro": "This installation report verifies that the WIPOTEC X-ray inspection system has been installed "
             "correctly and performs as required in quality-critical applications. It confirms compliance with the "
             "applicable standards and regulations for equipment in regulated environments and provides documentation "
             "suitable for the customer's Quality Management System and for the standard operating procedures (SOPs) "
             "used for periodic tests and maintenance.",
    "procedure": "The equipment referenced in this document has been installed in accordance with the WIPOTEC-XR Work Instruction.",
    "note": "N/A in this document means \"Not Applicable\".",
    "customer": "This section records the customer and site details for the installed equipment.",
    "system": "This section shows that the equipment has been received as ordered, that all documentation is present "
              "and that the system configuration is defined. Electrical values are the design specification of the "
              "machine, not measured readings.",
    "installation": "The Installation Checks ensure that the machine is installed correctly according to the machine "
                    "documentation and the customer specification.",
    "operation": "The Operation Checks ensure that the machine operates according to the machine documentation and the "
                 "customer specification. Power-up checks are performed with the default product of the machine "
                 "configuration.",
    "safety": "The following checks verify the safety circuit of the machine. Comment in the remark field if any check fails.",
    "product": "Products agreed with the customer are set up according to the relevant SOP and run for a minimum of "
               "4 hours and 1000 products. The expected False Reject Rate (FRR) is below 0.05 %.",
    "training": "The Training section confirms that the customer has received initial training on the machine and the "
                "required maintenance routine.",
    "disclaimer": "This document records the completion of the work performed by WIPOTEC on the subject device in "
                  "accordance with agreed standards. It does not guarantee the continued performance of the device. "
                  "Measurements recorded reflect the device's performance at the time of testing by WIPOTEC and, unless "
                  "explicitly stated otherwise, do not express an opinion on the sufficiency of customer-designed test "
                  "procedures. This document is not a warranty, either implied or express.",
    "original": "This document constitutes the original version. A certified electronic copy is maintained in WIPOTEC Singapore.",
}

# Yes/No lists (section 3)
YESNO_GROUPS = [
    {"id": "accessories", "title": "3.4 Accessories supplied with the machine", "items": [
        "All reject bin keys", "All X-ray enable keys", "Correct lamp stack and beacons (as per GA drawing)",
        "Keyboard", "Radiation meter"]},
    {"id": "documentation", "title": "3.5 Documentation", "items": [
        "Operator manual present", "Technical manual present", "Wiring diagram present",
        "EC Declaration of Conformity present", "Certificate of incorporation present",
        "Radiation certificate present", "Installation report present", "Registration document present"]},
    {"id": "training", "title": "6.1 Training given, understood and passed", "items": [
        "Machine condition and maintenance", "Machine operation", "Basic machine safety"]},
]

# Pass / Failed / N/A checklists
CHECK_SECTIONS = [
    {"id": "4.2", "title": "4.2 Visual Inspection", "items": [
        "Condition of cabinet", "Condition of cables / glands / gaskets", "Condition and alignment of cowls",
        "Condition of curtains / shutdown plates", "Condition of USB and RJ45 external sockets",
        "Condition of door seals", "Condition of screws and fittings", "Condition of bearings",
        "Condition of belts", "Condition of touch screen", "Condition of hinges and door locks",
        "Condition of fan / air conditioning unit", "Condition of all guide rails",
        "No oil leakage from the generator (visual check inside the cabinet)", "Condition of all rollers"]},
    {"id": "4.3", "title": "4.3 Mechanical Checks", "items": [
        "Machine mechanically installed according to the installation instructions in the machine documentation",
        "All belts in good condition, free of dirt and debris",
        "No intrusions within the X-ray beam path",
        "Guide rails correctly mounted to the machine and user adjustable",
        "Product handling and guiding correct for the machine type",
        "The machine is level",
        "All reject devices positioned and aligned correctly for the product flow",
        "Inspection belt correctly tracked and tensioned",
        "External infeed / outfeed belts level with the inspection belt",
        "Infeed and outfeed transfer to / from the inspection belt suitable for the product",
        "Encoder mounted as per the machine documentation using a decoupler",
        "Breather fitted to the generator",
        "Generator securely mounted in the cabinet"]},
    {"id": "4.4", "title": "4.4 Electrical Checks", "items": [
        "The machine is earthed / grounded",
        "Mains supply rated correctly for the machine type",
        "Incoming mains supply is stable",
        "All external cables routed correctly",
        "If required, a CVT and/or UPS is fitted to the machine and working correctly",
        "No evidence of static on the infeed and outfeed conveyor belts"]},
    {"id": "4.5", "title": "4.5 Machine Location", "items": [
        "Machine location acceptable and as described in the machine documentation",
        "All doors, panels and equipment can be used without obstruction",
        "IP rating correct for the environment and as per the machine documentation",
        "Ambient temperature and relative humidity within the machine specification",
        "Safety signage correct and in the local language"]},
    {"id": "5.1", "title": "5.1 Power Up Checks", "items": [
        "The machine powers on correctly and shows the software home page",
        "The touch screen is correctly calibrated",
        "Default product belt speed matches the conveyor speed and/or the encoder is correctly programmed"]},
    {"id": "5.3", "title": "5.3 Machine Functions", "items": [
        "Reject devices configured and tested correctly, with all associated sensors",
        "All pack sensors set up and configured as per the machine documentation and customer specification",
        "All peripherals installed, powered and configured in the machine software",
        "Machine integrated as described in the machine documentation and customer specification",
        "All lamps and beacon stack working as per the machine documentation and customer specification",
        "Product spacing as per the machine documentation",
        "Detector delays set correctly",
        "Inspection conveyor speed as per the machine documentation",
        "Image capture suitable for inspection",
        "All pre-agreed products configured; POD and FRR as described in the machine documentation",
        "All network disconnect alarms set as per the customer requirements",
        "Connectivity options configured correctly"]},
    {"id": "5.6", "title": "5.6 Backup and Images", "items": [
        "Full system backup / export taken",
        "Product exports or image folders of all products from the product set-up and performance verification saved",
        "All data stored by machine serial number on the WIPOTEC service server for future reference"]},
]

# Safety circuit devices (section 5.2): each fitted device gets its location and the tests below.
SAFETY_DEVICES = [
    {"id": "estop", "title": "Emergency Stop Buttons", "item": "Emergency Stop Button", "tests": [
        "With X-rays on, push the emergency stop button: X-rays turn off and the correct fault message is shown on the HMI",
        "With the emergency stop engaged, press conveyor start: the conveyors controlled by the X-ray do not run",
        "With the emergency stop engaged: all air dump solenoids controlled by the X-ray are OPEN",
        "With the emergency stop engaged: the correct I/O is shown in the software",
        "With the emergency stop engaged, power cycle the machine: the machine remains in fault state"]},
    {"id": "interlock", "title": "Interlocks", "item": "Interlock", "tests": [
        "With X-rays on, open the interlock: X-rays turn off and the correct fault message is shown on the HMI",
        "With the interlock open, press conveyor start: the conveyors controlled by the X-ray do not run",
        "With the interlock open: all air dump solenoids controlled by the X-ray are OPEN",
        "With the interlock open: the correct I/O is shown in the software",
        "With the interlock open, power cycle the machine: the machine remains in fault state"]},
    {"id": "lamp", "title": "X-Ray On Lamps", "item": "X-Ray On Lamp", "tests": [
        "With X-rays on, remove the X-ray on lamp: X-rays turn off and the correct fault message is shown on the HMI",
        "With the lamp removed, press conveyor start: the conveyors controlled by the X-ray do not run",
        "With the lamp removed: all air dump solenoids controlled by the X-ray are OPEN",
        "With the lamp removed: the X-ray ON I/O light is off",
        "With the lamp removed, power cycle the machine: the machine remains in fault state"]},
]

# Repeatable component tables in section 3: (key, title, item label, [(field, label)])
COMPONENTS = [
    ("detectors", "Detectors", "Detector", [("serial", "Serial Number"), ("type", "Detector Type"), ("width", "Width (mm)"),
                                           ("diode", "Diode Size (mm)"), ("part", "Part Number"), ("position", "Position")]),
    ("generators", "Generators", "Generator", [("kv", "kV"), ("ma", "mA"), ("wattage", "Wattage (W)"),
                                              ("serial", "Serial Number"), ("part", "Part Number"), ("position", "Position")]),
    ("curtains", "Curtains Fitted", "Curtain", [("material", "Curtain Material"), ("width", "Width (mm)"),
                                               ("length", "Drop / Length (mm)"), ("qty", "Quantity")]),
    ("belts", "Conveyor Belts", "Conveyor Belt", [("material", "Belt Material"), ("width", "Width (mm)"), ("length", "Length (mm)")]),
    ("test_samples", "Test Samples", "Test Sample", [("material", "Test Sample Material"), ("size", "Size (mm)"),
                                                    ("cert", "Certificate Number")]),
]
PRODUCT_FIELDS = [("name", "Product Library Name"), ("length", "Product Length (mm)"), ("width", "Product Width (mm)"),
                  ("weight", "Nominal Weight (g)"), ("ppm", "Packs per Minute"), ("gap", "Pack Gap (mm)"),
                  ("frr", "False Reject Rate FRR (%)"), ("passes", "Number of Product Passes"),
                  ("duration", "Duration of Product Run")]


# ------------------------------------------------------------
# Request model
# ------------------------------------------------------------
class SafetyDevice(BaseModel):
    location: str = ""
    results: List[str] = []
    remark: str = ""


class Photo(BaseModel):
    image: str = ""
    comment: str = ""


class XRIQData(BaseModel):
    doc_no: str = ""
    model: str = ""
    serial_no: str = ""
    asset_number: str = ""
    system_name: str = ""
    customer: Dict[str, str] = {}
    machine: Dict[str, str] = {}
    components: Dict[str, List[Dict[str, str]]] = {}
    yesno: Dict[str, Dict[str, str]] = {}
    operator_manual_language: str = ""
    technical_manual_language: str = ""
    qualification_purpose: str = ""
    checks: Dict[str, Dict[str, Dict[str, str]]] = {}
    mains_voltage: str = ""
    ambient_temp: str = ""
    humidity: str = ""
    location_photos: List[Photo] = []
    safety: Dict[str, List[SafetyDevice]] = {}
    global_estops: str = ""
    screen_photos: List[Photo] = []
    connectivity: str = ""
    connectivity_detail: str = ""
    ip_address: str = ""
    subnet_mask: str = ""
    gateway: str = ""
    safety_inspection: str = ""
    xrsc_cert_no: str = ""
    xrpv_cert_no: str = ""
    products: List[Dict[str, str]] = []
    trainees: List[Dict[str, str]] = []
    remarks: str = ""
    tech_name: str = ""
    tech_function: str = ""
    tech_date: str = ""
    tech_signature: str = ""
    cust_name: str = ""
    cust_function: str = ""
    cust_date: str = ""
    cust_signature: str = ""


# ------------------------------------------------------------
# Calculations
# ------------------------------------------------------------
def _num(v):
    try:
        return float(str(v).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def mains_check(v):
    """(text, css) - the measured mains voltage must fall inside one of the supported ranges."""
    n = _num(v)
    if n is None:
        return "", "na-text"
    for lo, hi, label in MAINS_RANGES:
        if lo <= n <= hi:
            return f"Within range ({label})", "pass-text"
    return "Outside the supported ranges", "fail-text"


def frr_check(v):
    n = _num(v)
    if n is None:
        return "", "na-text"
    return ("PASS (< 0.05 %)", "pass-text") if n < FRR_LIMIT else ("FAIL (≥ 0.05 %)", "fail-text")


def _cls(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("pass", "yes"):
        return "pass-text"
    if v in ("failed", "fail", "no"):
        return "fail-text"
    return "na-text"


# ------------------------------------------------------------
# PDF template
# ------------------------------------------------------------
XRIQ_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
  @page {
    size: A4; margin: 22mm 10mm 14mm 10mm;
    @top-left { content: "Document No.: {{ doc_css }}"; font-family: Arial, sans-serif; font-size: 8pt; color: #333; vertical-align: bottom; padding-bottom: 5px; }
    @top-right { content: url('{{ logo_top }}'); vertical-align: bottom; padding-bottom: 5px; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: Arial, sans-serif; font-size: 8pt; color: #555; }
    @bottom-left { content: "WIPOTEC X-Ray Installation & Qualification"; font-family: Arial, sans-serif; font-size: 7pt; color: #777; }
  }
  @page cover { margin: 14mm 12mm 12mm 12mm; @top-left { content: ""; } @top-right { content: ""; } @bottom-left { content: ""; } @bottom-right { content: ""; } }
  {{ base_css }}
  .cover { page: cover; page-break-after: always; break-after: page; height: 268mm; position: relative; }
  .cover-logo { text-align: right; }
  .cover-logo img { width: 190px; }
  .cover-title { margin-top: 45mm; font-size: 22pt; font-weight: bold; color: #1a1a1a; }
  .cover-title .slash { font-size: 22pt; }
  .cover-sub { font-size: 11pt; color: #007777; margin-top: 2mm; }
  .cover-info { margin-top: 12mm; width: 65%; border-collapse: collapse; }
  .cover-info td { padding: 5px 6px; font-size: 10pt; border-bottom: 1px solid #c2d6d6; }
  .cover-info td.k { width: 38%; font-weight: bold; color: #333; }
  .cover-foot { position: absolute; bottom: 0; left: 0; right: 0; border-top: 2px solid #009999; padding-top: 3mm; }
  .cover-foot table { width: 100%; border-collapse: collapse; }
  .cover-foot td { width: 50%; vertical-align: top; font-size: 7.5pt; line-height: 1.35; color: #333; }
  .cover-foot b { font-size: 8.5pt; }
  .chapter { page-break-before: always; break-before: page; }
  .chapter-title { font-size: 12pt; font-weight: bold; color: #000; margin: 0 0 6px; }
  .sub-head { font-weight: bold; color: #007777; font-size: 8.5pt; margin: 8px 0 3px; page-break-after: avoid; break-after: avoid; }
  .text-block { font-size: 7.5pt; margin: 2px 0 4px; }
  .res-col { width: 60px; text-align: center; font-weight: bold; }
  .rmk-col { width: 28%; }
  .two-col { width: 100%; border-collapse: collapse; }
  .two-col > tbody > tr > td { width: 50%; vertical-align: top; padding: 0 2px; }
  .comp th, .comp td { text-align: left; }
  .photo-grid { width: 100%; border-collapse: collapse; }
  .photo-grid td { width: 50%; vertical-align: top; padding: 3px; }
  .photo-box { border: 1px solid #c2d6d6; padding: 4px; text-align: center; page-break-inside: avoid; break-inside: avoid; }
  .photo-box img { max-width: 100%; max-height: 85mm; }
  .photo-box .cap { font-size: 7pt; color: #333; margin-top: 3px; text-align: left; }
  .sig-box img { max-height: 50px; max-width: 90%; }
  .sig-meta { width: 100%; border-collapse: collapse; margin-top: 4px; }
  .sig-meta td { font-size: 7.5pt; padding: 1px 4px; text-align: left; border: none; }
  .sig-meta td.k { width: 30%; font-weight: bold; color: #333; }
  .orig { font-size: 7pt; color: #666; margin-top: 8px; border-top: 1px solid #ddd; padding-top: 4px; }
</style></head>
<body>

{% macro head(t) %}<div class="section-header"><span class="slash" style="color:#fff;">/</span> {{ t }}</div>{% endmacro %}
{% macro checklist(sec) %}
<table class="checklist-table">
  <tr><th>Check</th><th class="res-col">Result</th><th class="rmk-col">Remark</th></tr>
  {% for it in sec["items"] %}{% set r = results[sec.id][it] %}
  <tr><td>{{ it }}</td><td class="res-col {{ cls(r.result) }}">{{ r.result }}</td><td>{{ r.remark }}</td></tr>
  {% endfor %}
</table>
{% endmacro %}
{% macro yesno_table(g) %}
<table class="checklist-table">
  <tr><th>Item</th><th class="res-col">Answer</th></tr>
  {% for it in g["items"] %}{% set a = yn[g.id][it] %}<tr><td>{{ it }}</td><td class="res-col {{ cls(a) }}">{{ a }}</td></tr>{% endfor %}
</table>
{% endmacro %}
{% macro photos(list) %}
{% if list %}
<table class="photo-grid">
  {% for row in list|batch(2) %}<tr>{% for p in row %}<td><div class="photo-box"><img src="{{ p.image }}">{% if p.comment %}<div class="cap">{{ p.comment }}</div>{% endif %}</div></td>{% endfor %}{% if row|length == 1 %}<td></td>{% endif %}</tr>{% endfor %}
</table>
{% endif %}
{% endmacro %}

{# ======================= COVER ======================= #}
<div class="cover">
  <div class="cover-logo"><img src="{{ logo_header }}" alt="WIPOTEC"></div>
  <div class="cover-title"><span class="slash">/</span> Installation &amp; Qualification Report</div>
  <div class="cover-sub">X-Ray Inspection System</div>
  <table class="cover-info">
    <tr><td class="k">Type</td><td>X-Ray</td></tr>
    <tr><td class="k">Model</td><td>{{ d.model or '—' }}</td></tr>
    <tr><td class="k">Serial Number</td><td><strong>{{ d.serial_no or '—' }}</strong></td></tr>
    <tr><td class="k">Asset Number</td><td>{{ d.asset_number or '—' }}</td></tr>
    <tr><td class="k">System Name</td><td>{{ d.system_name or '—' }}</td></tr>
    <tr><td class="k">Customer</td><td>{{ d.customer.name or '—' }}</td></tr>
    <tr><td class="k">Document No.</td><td>{{ d.doc_no or '—' }}</td></tr>
  </table>
  <div class="cover-foot"><table><tr>
    <td><b>WIPOTEC GmbH</b><br>Adam-Hoffmann-Straße 26<br>67657 Kaiserslautern<br>Phone: +49 631 34146-0<br>info@wipotec.com<br>www.wipotec.com</td>
    <td><b>WIPOTEC Singapore Pte Ltd.</b><br>German Centre for Industry &amp; Trade 25<br>International Business Park<br>#03-29 German Centre 609916 Singapore<br>T +65 690 80 358 / F +65 690 80 359<br>service.sea@wipotec.com</td>
  </tr></table></div>
</div>

{# ======================= 1-2 ======================= #}
<div class="chapter-title"><span class="slash">/</span> 1. Introduction</div>
<div class="section-block">
  {{ head('Description') }}
  <div class="text-block">{{ t.intro }}</div>
  <div class="text-block"><strong>Procedure Statement:</strong> {{ t.procedure }}</div>
  <div class="text-block"><strong>Note:</strong> {{ t.note }}</div>
</div>

<div class="chapter-title" style="margin-top:10px;"><span class="slash">/</span> 2. Customer Details</div>
<div class="section-block">
  {{ head('Customer Information') }}
  <div class="text-block">{{ t.customer }}</div>
  <table class="data-table">
    <tr><td class="label-col">Customer ID</td><td class="val-col">{{ c.customer_id }}</td><td class="label-col">Customer Name</td><td class="val-col"><strong>{{ c.name }}</strong></td></tr>
    <tr><td class="label-col">Address 1</td><td class="val-col">{{ c.address1 }}</td><td class="label-col">Address 2</td><td class="val-col">{{ c.address2 }}</td></tr>
    <tr><td class="label-col">Town / City</td><td class="val-col">{{ c.city }}</td><td class="label-col">State / Province</td><td class="val-col">{{ c.province }}</td></tr>
    <tr><td class="label-col">Zip / Postal Code</td><td class="val-col">{{ c.zip }}</td><td class="label-col">Country</td><td class="val-col">{{ c.country }}</td></tr>
    <tr><td class="label-col">Site Contact Name</td><td class="val-col">{{ c.contact }}</td><td class="label-col">Telephone</td><td class="val-col">{{ c.phone }}</td></tr>
    <tr><td class="label-col">Email Address 1</td><td class="val-col">{{ c.email1 }}</td><td class="label-col">Email Address 2</td><td class="val-col">{{ c.email2 }}</td></tr>
    <tr><td class="label-col">WIPOTEC Order Number</td><td class="val-col">{{ c.wipotec_order }}</td><td class="label-col">Customer PO Number</td><td class="val-col">{{ c.customer_po }}</td></tr>
  </table>
</div>
<div class="orig">{{ t.original }}</div>

{# ======================= 3. SYSTEM ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 3. System Information</div>
<div class="text-block">{{ t.system }}</div>
<div class="section-block">
  {{ head('3.1 Machine Details') }}
  <table class="data-table">
    <tr><td class="label-col">Machine Model</td><td class="val-col">{{ d.model }}</td><td class="label-col">Machine Serial Number</td><td class="val-col"><strong>{{ d.serial_no }}</strong></td></tr>
    <tr><td class="label-col">Machine Voltage (V)</td><td class="val-col">{{ m.voltage }}</td><td class="label-col">Machine Current (A)</td><td class="val-col">{{ m.current }}</td></tr>
    <tr><td class="label-col">Frequency (Hz)</td><td class="val-col">{{ m.frequency }}</td><td class="label-col">Air Pressure (bar)</td><td class="val-col">{{ m.air_pressure }}</td></tr>
    <tr><td class="label-col">Date of Manufacture</td><td class="val-col">{{ m.date_of_manufacture }}</td><td class="label-col">Software Type / Version</td><td class="val-col">{{ m.software_type }} {{ m.software_version }}</td></tr>
    <tr><td class="label-col">PC Part Number</td><td class="val-col">{{ m.pc_part }}</td><td class="label-col">PC Serial Number</td><td class="val-col">{{ m.pc_serial }}</td></tr>
  </table>
</div>
{% for key, title, label, fields in components %}{% set rows = comp[key] %}
{% if rows %}
<div class="section-block">
  {% if loop.index == 1 %}{{ head('3.2 Detectors and Generators') }}{% elif loop.index == 3 %}{{ head('3.3 Curtains, Belts and Test Samples') }}{% endif %}
  <div class="sub-head">{{ title }} ({{ rows|length }})</div>
  <table class="checklist-table comp">
    <tr><th style="width:40px;">No.</th>{% for f, l in fields %}<th>{{ l }}</th>{% endfor %}</tr>
    {% for r in rows %}<tr><td>{{ loop.index }}</td>{% for f, l in fields %}<td>{{ r[f] }}</td>{% endfor %}</tr>{% endfor %}
  </table>
</div>
{% endif %}
{% endfor %}
<table class="two-col"><tr>
  <td><div class="section-block">{{ head(yesno_groups[0].title) }}{{ yesno_table(yesno_groups[0]) }}</div></td>
  <td><div class="section-block">{{ head(yesno_groups[1].title) }}{{ yesno_table(yesno_groups[1]) }}
    <table class="data-table" style="margin-top:3px;">
      <tr><td class="label-col">Operator Manual Language</td><td class="val-col">{{ d.operator_manual_language }}</td></tr>
      <tr><td class="label-col">Technical Manual Language</td><td class="val-col">{{ d.technical_manual_language }}</td></tr>
    </table></div></td>
</tr></table>
<div class="orig">{{ t.original }}</div>
</div>

{# ======================= 4. INSTALLATION ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 4. Installation Checks</div>
<div class="text-block">{{ t.installation }}</div>
<table class="data-table"><tr><td class="label-col">4.1 Purpose of Qualification</td><td class="val-col"><strong>{{ d.qualification_purpose }}</strong></td></tr></table>
{% for sec in check_sections if sec.id.startswith('4.') %}
<div class="section-block">
  {{ head(sec.title) }}
  {% if sec.id == '4.4' %}
  <table class="data-table">
    <tr><td class="label-col">Actual Mains Voltage Supplied (V)</td><td class="val-col"><strong>{{ d.mains_voltage }}</strong></td><td class="val-col {{ mains[1] }}">{{ mains[0] }}</td></tr>
    <tr><td colspan="3" class="val-col" style="font-size:7pt;color:#555;">The measured mains voltage must fall within one of these ranges: 208 – 250 V AC / 50-60 Hz / 6 A max, or 110 – 120 V AC / 50-60 Hz / 10 A max.</td></tr>
  </table>
  {% endif %}
  {% if sec.id == '4.5' %}
  <table class="data-table">
    <tr><td class="label-col">Ambient Temperature (°C)</td><td class="val-col">{{ d.ambient_temp }}</td><td class="label-col">Relative Humidity (%)</td><td class="val-col">{{ d.humidity }}</td></tr>
  </table>
  {% endif %}
  {{ checklist(sec) }}
</div>
{% if sec.id == '4.5' and d.location_photos %}<div class="sub-head">Machine Location Photos</div>{{ photos(d.location_photos) }}{% endif %}
{% endfor %}
<div class="orig">{{ t.original }}</div>
</div>

{# ======================= 5. OPERATION ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 5. Operation Checks</div>
<div class="text-block">{{ t.operation }}</div>
<div class="section-block">{{ head(check_sections_by_id['5.1'].title) }}{{ checklist(check_sections_by_id['5.1']) }}</div>

{{ head('5.2 Safety Circuit') }}
<div class="text-block">{{ t.safety }}</div>
{% for dev in safety_devices %}{% set units = safety[dev.id] %}
<div class="sub-head">{{ dev.title }} — {{ units|length }} fitted</div>
{% for u in units %}
<div class="section-block">
  <table class="checklist-table">
    <tr><th>{{ dev.item }} {{ loop.index }}{% if u.location %} — Location: {{ u.location }}{% endif %}</th><th class="res-col">Result</th></tr>
    {% for test in dev.tests %}{% set r = u.results[loop.index0] if loop.index0 < u.results|length else '-' %}
    <tr><td>{{ test }}</td><td class="res-col {{ cls(r) }}">{{ r or '-' }}</td></tr>{% endfor %}
    {% if u.remark %}<tr><td colspan="2"><strong>Remark:</strong> {{ u.remark }}</td></tr>{% endif %}
  </table>
</div>
{% endfor %}
{% endfor %}
<table class="data-table"><tr><td class="label-col">Global emergency stop buttons connected (per machine documentation and customer specification)</td><td class="val-col">{{ d.global_estops }}</td></tr></table>
{% if d.screen_photos %}<div class="sub-head">Detector Install Settings, Diagnostics and I/O</div>{{ photos(d.screen_photos) }}{% endif %}

<div class="section-block">
  {{ head(check_sections_by_id['5.3'].title) }}{{ checklist(check_sections_by_id['5.3']) }}
  <table class="data-table" style="margin-top:3px;">
    <tr><td class="label-col">Connectivity Option</td><td class="val-col">{{ d.connectivity }}{% if d.connectivity_detail %} — {{ d.connectivity_detail }}{% endif %}</td><td class="label-col">IP Address</td><td class="val-col">{{ d.ip_address }}</td></tr>
    <tr><td class="label-col">Subnet Mask</td><td class="val-col">{{ d.subnet_mask }}</td><td class="label-col">Gateway Address</td><td class="val-col">{{ d.gateway }}</td></tr>
  </table>
</div>

<div class="section-block">
  {{ head('5.4 Radiation Safety and Performance Verification') }}
  <table class="data-table">
    <tr><td class="label-col">Radiation safety inspection passed?</td><td class="val-col {{ cls(d.safety_inspection) }}">{{ d.safety_inspection }}</td></tr>
    <tr><td class="label-col">Radiation Safety (XRSC) Certificate No.</td><td class="val-col">{{ d.xrsc_cert_no }}</td></tr>
    <tr><td class="label-col">Performance Verification (XRPV) Certificate No.</td><td class="val-col">{{ d.xrpv_cert_no }}</td></tr>
  </table>
</div>

<div class="section-block">
  {{ head('5.5 Product Set-Up') }}
  <div class="text-block">{{ t.product }}</div>
</div>
{% for p in products %}
<div class="section-block">
  <div class="sub-head">Product {{ loop.index }}{% if p.v.name %} — {{ p.v.name }}{% endif %}</div>
  <table class="data-table" style="table-layout: fixed;">
    <tr><td class="label-col">Product Length (mm)</td><td class="val-col">{{ p.v.length }}</td><td class="label-col">Product Width (mm)</td><td class="val-col">{{ p.v.width }}</td></tr>
    <tr><td class="label-col">Nominal Weight (g)</td><td class="val-col">{{ p.v.weight }}</td><td class="label-col">Packs per Minute</td><td class="val-col">{{ p.v.ppm }}</td></tr>
    <tr><td class="label-col">Pack Gap (mm)</td><td class="val-col">{{ p.v.gap }}</td><td class="label-col">False Reject Rate (%)</td><td class="val-col">{{ p.v.frr }} <span class="{{ p.frr_cls }}">{{ p.frr_txt }}</span></td></tr>
    <tr><td class="label-col">Number of Product Passes</td><td class="val-col">{{ p.v.passes }}</td><td class="label-col">Duration of Product Run</td><td class="val-col">{{ p.v.duration }}</td></tr>
  </table>
</div>
{% endfor %}
<div class="section-block">{{ head(check_sections_by_id['5.6'].title) }}{{ checklist(check_sections_by_id['5.6']) }}</div>
<div class="orig">{{ t.original }}</div>
</div>

{# ======================= 6-7 ======================= #}
<div class="chapter">
<div class="chapter-title"><span class="slash">/</span> 6. Training</div>
<div class="text-block">{{ t.training }}</div>
<div class="section-block">{{ head(yesno_groups[2].title) }}{{ yesno_table(yesno_groups[2]) }}</div>
<div class="section-block">
  <div class="sub-head">Trained Personnel ({{ d.trainees|length }})</div>
  <table class="checklist-table">
    <tr><th style="width:40px;">No.</th><th>First Name</th><th>Family Name</th><th>Position</th><th>Date</th></tr>
    {% for tr in d.trainees %}<tr><td>{{ loop.index }}</td><td>{{ tr.first }}</td><td>{{ tr.family }}</td><td>{{ tr.position }}</td><td>{{ tr.date }}</td></tr>{% endfor %}
  </table>
</div>

<div class="chapter-title" style="margin-top:12px;"><span class="slash">/</span> 7. Completion and Sign-off</div>
{% if d.remarks %}<div class="section-block">{{ head('Remarks') }}<div class="text-block">{{ d.remarks }}</div></div>{% endif %}
<div class="section-block">
  <table class="signature-table"><tr>
    <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">WIPOTEC Representative</div>
      {% if d.tech_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ d.tech_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
      <table class="sig-meta"><tr><td class="k">Name :</td><td>{{ d.tech_name }}</td></tr><tr><td class="k">Function :</td><td>{{ d.tech_function }}</td></tr><tr><td class="k">Date :</td><td>{{ d.tech_date }}</td></tr></table></div></td>
    <td><div class="sig-box"><div style="font-weight:bold;color:#009999;">Customer Review and Approval</div>
      {% if d.cust_signature %}<div style="height:50px;margin-top:6px;"><img src="{{ d.cust_signature }}" /></div>{% else %}<div class="sig-line"></div>{% endif %}
      <table class="sig-meta"><tr><td class="k">Name :</td><td>{{ d.cust_name }}</td></tr><tr><td class="k">Function :</td><td>{{ d.cust_function }}</td></tr><tr><td class="k">Date :</td><td>{{ d.cust_date }}</td></tr></table></div></td>
  </tr></table>
</div>
<div class="text-block" style="margin-top:8px;color:#555;">{{ t.disclaimer }}</div>
<div class="orig">{{ t.original }}</div>
</div>
</body></html>
"""


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------
@router.get("/xray-installation.html")
def serve_xriq_html():
    return FileResponse(XRIQ_HTML_PATH)


@router.get("/xriq-config")
def xriq_config():
    return {
        "results": RESULTS,
        "yesno": YESNO,
        "qualification_purposes": QUALIFICATION_PURPOSES,
        "connectivity": CONNECTIVITY,
        "mains_ranges": [[lo, hi, label] for lo, hi, label in MAINS_RANGES],
        "frr_limit": FRR_LIMIT,
        "yesno_groups": YESNO_GROUPS,
        "check_sections": CHECK_SECTIONS,
        "safety_devices": SAFETY_DEVICES,
        "components": [{"key": k, "title": t, "item": i, "fields": [{"key": f, "label": l} for f, l in fs]}
                       for k, t, i, fs in COMPONENTS],
        "product_fields": [{"key": f, "label": l} for f, l in PRODUCT_FIELDS],
    }


@router.post("/generate-xriq-pdf")
def generate_xriq_pdf(data: XRIQData):
    try:
        logger.info(f"Generate XRIQ PDF requested for doc_no={data.doc_no!r}")
        pdf = _build_xriq_pdf(data)
        logger.info(f"XRIQ PDF generated successfully for doc_no={data.doc_no!r} ({len(pdf)} bytes)")
    except Exception as e:
        logger.error(f"XRIQ PDF generation failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500,
                            content={"detail": f"PDF generation failed: {type(e).__name__}: {e}"})
    name = f"XRIQ_Report_{safe_filename_part(data.doc_no)}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(name)})


def _build_xriq_pdf(data: XRIQData) -> bytes:
    d = data.model_dump() if hasattr(data, "model_dump") else data.dict()

    results = {}
    for s in CHECK_SECTIONS:
        sent = data.checks.get(s["id"], {})
        results[s["id"]] = {it: {"result": sent.get(it, {}).get("result") or "-",
                                 "remark": sent.get(it, {}).get("remark", "")} for it in s["items"]}
    yn = {g["id"]: {it: (data.yesno.get(g["id"], {}).get(it) or "-") for it in g["items"]} for g in YESNO_GROUPS}
    comp = {k: [{f: (r.get(f, "") or "") for f, _ in fs} for r in data.components.get(k, [])
                if any((r.get(f) or "").strip() for f, _ in fs)]
            for k, _, _, fs in COMPONENTS}
    safety = {dev["id"]: [u.model_dump() if hasattr(u, "model_dump") else u.dict()
                          for u in data.safety.get(dev["id"], [])] for dev in SAFETY_DEVICES}
    products = []
    for p in data.products:
        if not any((v or "").strip() for v in p.values()):
            continue
        txt, css = frr_check(p.get("frr"))
        products.append({"v": {f: p.get(f, "") for f, _ in PRODUCT_FIELDS}, "frr_txt": txt, "frr_cls": css})
    d["location_photos"] = [p for p in d["location_photos"] if str(p.get("image", "")).startswith("data:image/")]
    d["screen_photos"] = [p for p in d["screen_photos"] if str(p.get("image", "")).startswith("data:image/")]
    d["trainees"] = [t for t in d["trainees"] if any((v or "").strip() for v in t.values())]
    d["customer"] = {k: d["customer"].get(k, "") for k in
                     ["customer_id", "name", "address1", "address2", "city", "province", "zip", "country",
                      "contact", "phone", "email1", "email2", "wipotec_order", "customer_po"]}

    doc_css = data.doc_no.replace("\\", "").replace('"', "").replace("\n", " ")
    html = Template(XRIQ_TEMPLATE).render(
        d=d, c=d["customer"], m=d["machine"], t=TEXT, results=results, yn=yn, comp=comp, safety=safety,
        products=products, components=COMPONENTS, yesno_groups=YESNO_GROUPS, check_sections=CHECK_SECTIONS,
        check_sections_by_id={s["id"]: s for s in CHECK_SECTIONS}, safety_devices=SAFETY_DEVICES,
        mains=mains_check(data.mains_voltage), cls=_cls, doc_css=doc_css, base_css=BASE_CSS,
        logo_top=LOGO_TOP_URI, logo_header=LOGO_HEADER_URI,
    )
    return weasyprint.HTML(string=html).write_pdf()
