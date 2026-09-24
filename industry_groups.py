"""Map NEEQ stock codes to three industry groups using local PDF folders."""
from __future__ import annotations

import os
from pathlib import Path

GROUP_MANUFACTURING = "制造"
GROUP_SOFTWARE = "软件信息"
GROUP_OTHER = "其他"
GROUP_ORDER = [GROUP_MANUFACTURING, GROUP_SOFTWARE, GROUP_OTHER]

PDF_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "pdf")


def normalize_code(value):
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text.isdigit():
        return text.zfill(6)
    return text


def group_from_folder(folder_name):
    """Collapse CSRC-style folder names into 制造 / 软件信息 / 其他."""
    name = folder_name or ""
    if name.startswith("01_") or "制造业" in name:
        return GROUP_MANUFACTURING
    if name.startswith("02_") or "软件和信息技术" in name:
        return GROUP_SOFTWARE
    return GROUP_OTHER


def folder_rank(folder_name):
    """Prefer an explicit CSRC folder over 待分类 or the PDF root."""
    name = folder_name or ""
    group = group_from_folder(name)
    if group != GROUP_OTHER:
        return 40
    if len(name) >= 2 and name[:2].isdigit() and not name.startswith("00"):
        return 30
    if name.startswith("00"):
        return 10
    return 0


def _code_from_pdf_name(filename):
    stem = os.path.basename(filename)
    if not stem.lower().endswith(".pdf"):
        return None
    code = stem.split("_")[0]
    if not code or not any(ch.isdigit() for ch in code):
        return None
    return normalize_code(code)


def scan_pdf_folders(pdf_root):
    """Return stock_code -> folder name, keeping the highest-rank folder."""
    root = Path(pdf_root)
    mapping = {}
    if not root.is_dir():
        return mapping

    def consider(code, folder):
        current = mapping.get(code)
        if current is None or folder_rank(folder) > folder_rank(current):
            mapping[code] = folder

    for pdf in root.glob("*.pdf"):
        code = _code_from_pdf_name(pdf.name)
        if code:
            consider(code, "")
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        for pdf in child.glob("*.pdf"):
            code = _code_from_pdf_name(pdf.name)
            if code:
                consider(code, child.name)
    return mapping


def assign_industries(stock_codes, pdf_root=None):
    """List of dicts: stock_code, industry_raw, industry."""
    pdf_root = pdf_root or PDF_DIR_DEFAULT
    mapping = scan_pdf_folders(pdf_root)
    rows = []
    for raw in stock_codes:
        code = normalize_code(raw)
        folder = mapping.get(code, "")
        rows.append(
            {
                "stock_code": code,
                "industry_raw": folder,
                "industry": group_from_folder(folder),
            }
        )
    return rows
