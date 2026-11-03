# Shared logo images (base64 PNG data URIs) used by every PDF template.
LOGO_TOP_URI = "data:image/png;base64,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"
LOGO_HEADER_URI = "data:image/png;base64,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"

# Shared table/section styling for all Wipotec PDF templates.
BASE_CSS = r"""
  *, *::before, *::after { box-sizing: border-box; }

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
"""
