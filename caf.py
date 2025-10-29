# caf.py — CAF Extractor (Forms + Text + OCR, y-position row mapping)
# Run: streamlit run caf.py

import re
from io import BytesIO
from typing import Dict, List, Tuple, Any
import pandas as pd
import streamlit as st

import fitz  # PyMuPDF
from pdf2image import convert_from_bytes
import pytesseract
import numpy as np
from PIL import Image

# Configure pytesseract for Streamlit Cloud (best effort)
try:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
except Exception:
    pass

# ---------------- Streamlit page config ----------------
st.set_page_config(page_title="CAF Extractor (Robust)", layout="wide")
st.title("Course Approval Form → Table")
st.caption(
    "Uploads a CAF PDF and extracts fields via Form Fields → Text → OCR (fallback). "
    "Rows aligned by vertical position, approval logic inferred from signatures."
)

# ---------------- Utilities ----------------
def norm_space(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[\u200b\ufeff\u00a0]", " ", s)
    return s

def clean_course_text(t: str) -> str:
    # Remove trailing "Link to course description" style text and collapse spaces
    t = t.replace("\n", " ").strip()
    t = re.sub(r"\s*Link to course description.*$", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t.strip(" -:")

def parse_course_code_and_title(course_text: str) -> tuple:
    """
    Try to split a raw line like:
    - 'POLI 3003 PRAG The Rise and Fall ...'
    - 'BBLCO1221U – Corporate Finance'
    - 'FI 356 - International Financial Markets and Investments'
    - '(GI) Econ 3006 PRCZ Economics of the European Union'
    into (course_code, course_title).
    """
    if not course_text:
        return "", ""

    text = course_text.strip()

    # Pattern: "(GI) Econ 3006 PRCZ Economics of the European Union"
    match1 = re.match(r"^\(([A-Z]+)\)\s+([A-Za-z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", text)
    if match1:
        prefix = match1.group(1)
        code = match1.group(2)
        title = match1.group(3)
        return f"({prefix}) {code}", title

    # Variant with separated subject and code blocks
    match1a = re.match(r"^\(([A-Z]+)\)\s+([A-Z]{2,4})\s+(\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", text)
    if match1a:
        prefix = match1a.group(1)
        subj = match1a.group(2)
        code_part = match1a.group(3)
        title = match1a.group(4)
        return f"({prefix}) {subj} {code_part}", title

    # Pattern: "POLI 3003 PRAG The Rise and Fall ..."
    match2 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", text)
    if match2:
        return match2.group(1).strip(), match2.group(2).strip()

    # Pattern: "CU 270: Culture and Cuisine"
    match3 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}[A-Z]?)\s*:\s*(.+)$", text)
    if match3:
        return match3.group(1).strip(), match3.group(2).strip()

    # Pattern: "CU 270-01 - 2163268-Culture and Cuisine"
    match4 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}(?:-\d{2})?)\s*-\s*(\d{7})-(.+)$", text)
    if match4:
        code = match4.group(1).strip()
        title = match4.group(3).strip()
        return code, title

    # Pattern: "BOCCONI 30150 - Introduction to Options and Futures"
    match4b = re.match(r"^([A-Z]{2,8}\s+\d{2,5})\s*-\s*(.+)$", text)
    if match4b:
        return match4b.group(1).strip(), match4b.group(2).strip()

    # Pattern: "FI 356 - International Financial Markets and Investments"
    match4c = re.match(r"^([A-Z]{2,4}\s+\d{2,4})\s*-\s*(.+)$", text)
    if match4c:
        return match4c.group(1).strip(), match4c.group(2).strip()

    # Pattern: "BBLCO1221U – Corporate Finance" (en dash / hyphen)
    match4a = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)\s*[–-]\s*(.+)$", text)
    if match4a:
        return match4a.group(1).strip(), match4a.group(2).strip()

    # Pattern: "BA-BHAAV1058U Management Accounting ..."
    match5 = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)\s+(.+)$", text)
    if match5:
        return match5.group(1).strip(), match5.group(2).strip()

    # Pattern: "ASIA2041 - Mainland Southeast Asia"
    match6 = re.match(r"^([A-Z]{1,4}(?:/[A-Z]{1,4})?\s*\d{2,3}[A-Z]?)\s*[-–]\s*(.+)$", text)
    if match6:
        return match6.group(1).strip(), match6.group(2).strip()

    # Pattern: "PO/EC 246 European Union Policies in Practice"
    match6a = re.match(r"^([A-Z]{1,4}/[A-Z]{1,4}\s+\d{2,4})\s+(.+)$", text)
    if match6a:
        return match6a.group(1).strip(), match6a.group(2).strip()

    # Fallback: guess first token is code
    code_guess = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)", text)
    if code_guess:
        code = code_guess.group(1).strip()
        title = text.replace(code, "").strip(" -:").strip()
        return code, title

    return "", text

def detect_signature_in_widgets(
    widgets: List[Dict],
    course_y: float,
    page: int,
    y_tolerance: float = 15.0
) -> Dict[str, bool]:
    """
    Look at PDF widgets close to the course row.
    Decide if those widgets look like they contain a signature
    (elective vs major/minor).
    """
    signature_detected = {"elective": False, "major_minor": False}

    for widget in widgets:
        if widget["page"] != page:
            continue
        if abs(widget["y0"] - course_y) > y_tolerance:
            continue

        widget_name = (widget["name"] or "").lower()
        widget_value = (widget["value"] or "").strip()

        has_signature = False

        # text in the box that looks like initials/names (not just No/N/A/etc.)
        if widget_value:
            non_sig_values = ["", "no", "n", "none", "yes", "y", "approved", "denied", "na", "n/a"]
            if widget_value.lower().strip() not in non_sig_values:
                if (
                    len(widget_value.strip()) > 1
                    and (any(c.isalpha() for c in widget_value) or any(c in widget_value for c in [".", ",", " "]))
                ):
                    has_signature = True

        # heuristic: if the widget name itself implies an approval box
        if not has_signature and widget_name:
            if "elec" in widget_name or "major" in widget_name or "minor" in widget_name:
                has_signature = True

        # map
        if "elec" in widget_name and has_signature:
            signature_detected["elective"] = True
        elif ("major" in widget_name or "minor" in widget_name) and has_signature:
            signature_detected["major_minor"] = True

    return signature_detected

def map_approval_type_from_signatures(
    signature_detected: Dict[str, bool],
    elective_approval: str,
    major_minor_approval: str,
    comments: str = ""
) -> str:
    """
    Turn signature + text context into final label:
    "Elective", "Major, Minor", "Not Approved", etc.
    """
    result = []

    # Priority 1: visual/structural signatures near row
    if signature_detected["elective"] and elective_approval:
        result.append("Elective")
    if signature_detected["major_minor"] and major_minor_approval:
        result.append("Major, Minor")

    # Priority 2: comments with patterns
    if not result and comments:
        c_low = comments.lower()
        if any(term in c_low for term in ["intr:", "ppd", "gon", "pac"]):
            result.append("Major, Minor")

    # Priority 3: fallback to field values
    if not result:
        if elective_approval and elective_approval.strip().lower() not in ["", "no", "n", "none"]:
            result.append("Elective")
        if major_minor_approval and major_minor_approval.strip().lower() not in ["", "no", "n", "none"]:
            result.append("Major, Minor")

    # Priority 4: comments override (Not Approved)
    if comments:
        c_low = comments.lower()
        if any(term in c_low for term in ["not approved", "denied", "rejected"]):
            result = ["Not Approved"]
        elif not result:
            if any(term in c_low for term in ["elective", "general elective", "elective only"]):
                result.append("Elective")
            elif any(term in c_low for term in ["major", "minor", "major/minor"]):
                result.append("Major, Minor")

    # Final merge
    return ", ".join(result) if result else ""

def extract_program_info(program_text: str) -> tuple:
    """
    Try to infer (Program/University, City, Country) from header program text.
    """
    if not program_text:
        return "", "", ""

    program_lower = program_text.lower()

    city_country_map = {
        "milan": ("Milan", "Italy"),
        "barcelona": ("Barcelona", "Spain"),
        "madrid": ("Madrid", "Spain"),
        "london": ("London", "United Kingdom"),
        "paris": ("Paris", "France"),
        "florence": ("Florence", "Italy"),
        "rome": ("Rome", "Italy"),
        "prague": ("Prague", "Czech Republic"),
        "copenhagen": ("Copenhagen", "Denmark"),
        "stockholm": ("Stockholm", "Sweden"),
        "dublin": ("Dublin", "Ireland"),
        "amsterdam": ("Amsterdam", "Netherlands"),
        "berlin": ("Berlin", "Germany"),
        "tokyo": ("Tokyo", "Japan"),
        "sydney": ("Sydney", "Australia"),
        "buenos aires": ("Buenos Aires", "Argentina"),
        "cape town": ("Cape Town", "South Africa"),
        "hong kong": ("Hong Kong", "China"),
        "singapore": ("Singapore", "Singapore"),
        "seoul": ("Seoul", "South Korea"),
        "kyoto": ("Kyoto", "Japan"),
        "nagoya": ("Nagoya", "Japan"),
        "waseda": ("Tokyo", "Japan"),
        "yonsei": ("Seoul", "South Korea"),
        "leeds": ("Leeds", "United Kingdom"),
        "bristol": ("Bristol", "United Kingdom"),
        "york": ("York", "United Kingdom"),
        "auckland": ("Auckland", "New Zealand"),
        "cairo": ("Cairo", "Egypt"),
        "munich": ("Munich", "Germany"),
        "christchurch": ("Christchurch", "New Zealand"),
    }

    # IES Abroad, CIEE patterns
    if "ies abroad" in program_lower or "ies " in program_lower:
        for key, (cty, ctry) in city_country_map.items():
            if key in program_lower:
                return program_text, cty, ctry
        return program_text, "", ""

    if "ciee" in program_lower:
        for key, (cty, ctry) in city_country_map.items():
            if key in program_lower:
                return program_text, cty, ctry
        return program_text, "", ""

    # generic city best-effort
    for key, (cty, ctry) in city_country_map.items():
        if key in program_lower:
            return program_text, cty, ctry

    return program_text, "", ""

COURSE_LINE_RE = re.compile(
    r"^\([A-Z]+\)\s+[A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4}\s+.+|"
    r"^[A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4}\s+.+|"
    r"^[A-Z]{2,4}\s+\d{2,4}[A-Z]?\s*[:\-–]\s*.+|"
    r"^[A-Z]{2,4}\s+\d{2,4}(?:-\d{2})?\s*-\s*\d{7}-.+|"
    r"^[A-Z]{2,8}\s+\d{2,5}\s*-\s*.+|"
    r"^[A-Z]{2,4}\s+\d{2,4}\s*-\s*.+|"
    r"^[A-Z]{2,10}(?:-[A-Z0-9]+)*\d+[A-Z0-9]*\s*[–-]\s*.+|"
    r"^[A-Z]{1,4}/[A-Z]{1,4}\s+\d{2,4}\s+.+",
    re.M
)

TERM_RE = re.compile(r"\b(fall|spring|summer|winter)\b", re.I)
DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

def ocr_text(pdf_bytes: bytes, dpi: int = 300) -> str:
    images = convert_from_bytes(pdf_bytes, dpi=dpi)
    parts = []
    for img in images:
        parts.append(pytesseract.image_to_string(img))
    return norm_space("\n".join(parts))

# ---------------- PDF reading helpers ----------------
def read_form_widgets(pdf_bytes: bytes):
    """
    widgets: [{name,value,x0,y0,x1,y1,page}, ...]
    fields:  {name:value, ...}
    """
    widgets = []
    fields = {}
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for p in doc:
            for w in p.widgets() or []:
                name = (w.field_name or "").strip()
                value = norm_space(w.field_value or "")
                rect = w.rect or fitz.Rect(0,0,0,0)
                item = {
                    "name": name,
                    "value": value,
                    "x0": rect.x0,
                    "y0": rect.y0,
                    "x1": rect.x1,
                    "y1": rect.y1,
                    "page": p.number
                }
                widgets.append(item)
                if name:
                    fields[name] = value
    return widgets, fields

def page_blocks(pdf_bytes: bytes):
    """
    Returns list of text blocks for each page with geometry.
    """
    blocks = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for p in doc:
            for b in p.get_text("blocks") or []:
                x0, y0, x1, y1, text, *_ = b
                blocks.append({
                    "page": p.number,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "text": text or ""
                })
    return blocks

def extract_courses_by_blocks(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Scan visible text blocks for lines that look like course listings.
    Tries to join multi-line titles.
    """
    exclude_patterns = [
        r"^THE\s+COLLEGE",
        r"^COURSE\s+APPROVAL",
        r"^IES\s+Abroad",
        r"^DEPARTMENT\s+OR\s+OFFICE",
        r"^STUDENTS\s+Complete",
        r"^AUTHORIZED\s+APPROVERS",
        r"^HOW\s+TO\s+TRANSFER",
        r"^FORM\s*$",
        r"^APPROVAL\s*$",
        r"^COLLEGE\s*$",
        r"^COURSE\s*$",
        r"^USE\s+ONLY\s*$",
        r"^ONLY\s*$"
    ]

    rows = []
    for b in page_blocks(pdf_bytes):
        txt = b["text"]
        if not txt:
            continue
        lines = txt.splitlines()
        i = 0
        while i < len(lines):
            line_clean = lines[i].strip()
            if COURSE_LINE_RE.match(line_clean):
                # skip if looks like header
                skip = False
                for patt in exclude_patterns:
                    if re.match(patt, line_clean, re.I):
                        skip = True
                        break
                full_text = line_clean
                if not skip:
                    # include next line if it's continuation
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if (
                            next_line
                            and not COURSE_LINE_RE.match(next_line)
                            and not any(re.match(patt, next_line, re.I) for patt in exclude_patterns)
                            and len(next_line) > 3
                        ):
                            full_text += " " + next_line
                            i += 1
                    rows.append({
                        "page": b["page"],
                        "x0": b["x0"],
                        "x1": b["x1"],
                        "y": b["y0"],  # top Y of the block
                        "Course": clean_course_text(full_text)
                    })
            i += 1

    # Deduplicate by (page, y, text)
    out = []
    seen = set()
    for r in sorted(rows, key=lambda x: (x["page"], round(x["y"], 1))):
        key = (r["page"], round(r["y"], 1), r["Course"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out

def nearest_by_y(
    target_y: float,
    items: List[Dict[str, Any]],
    page: int,
    y_tol: float = 8.0
):
    """
    Find item from items (which include y0/page/value)
    closest in vertical position to target_y.
    """
    best = None
    best_d = 1e9
    for it in items:
        if it["page"] != page:
            continue
        d = abs(it["y0"] - target_y)
        if d < best_d:
            best_d = d
            best = it
    if best and best_d <= y_tol:
        return best
    return None

def extract_approval_data_from_text_blocks(
    pdf_bytes: bytes,
    course_y: float,
    page: int,
    y_tolerance: float = 30.0
) -> Dict[str, str]:
    """
    Heuristic approach for handwritten/ink signatures and UR equivalent
    that appear as plain text near the course line.
    """
    approval_data = {
        "elective": "",
        "major_minor": "",
        "comments": "",
        "ur_equivalent": ""
    }

    blocks = page_blocks(pdf_bytes)

    nearby_blocks = [
        b for b in blocks
        if b["page"] == page and abs(b["y0"] - course_y) <= y_tolerance
    ]

    for block in nearby_blocks:
        text = block["text"].strip()
        if not text:
            continue
        lower_text = text.lower()

        # elective-ish
        if any(term in lower_text for term in [
            "general elective", "elective only", "rohan", "palma", "rp"
        ]):
            approval_data["elective"] = text

        # major/minor-ish
        if (
            any(term in lower_text for term in ["intr:", "major", "minor"])
            and not any(term in lower_text for term in ["elective", "general elective", "elective only"])
        ):
            approval_data["major_minor"] = text

        # Detect UR equivalent pattern like "FIN 224" / "N/A"
        # crude pattern: looks like 2-4 letters + number, or "N/A"
        if (
            re.match(r"^[A-Z]{2,4}\s+\d{2,4}$", text.strip())
            or text.strip().upper() == "N/A"
        ):
            approval_data["ur_equivalent"] = text.strip()

        # comments
        if any(term in lower_text for term in [
            "general elective", "elective only", "not approved", "approved"
        ]):
            approval_data["comments"] = text

    return approval_data

# ---------------- Header inference ----------------
def infer_header_from_fields(fields: Dict[str, str], pdf_bytes: bytes = None) -> Dict[str, str]:
    fd = {(k or "").strip().lower(): norm_space(v) for k, v in (fields or {}).items()}

    def pick_by_key(keys, avoid=None, value_re=None):
        avoid = avoid or []
        for k, v in fd.items():
            if not v:
                continue
            if any(key in k for key in keys) and not any(bad in k for bad in avoid):
                if value_re and not re.search(value_re, v, re.I):
                    continue
                return v
        return ""

    # Name
    name = pick_by_key(["name"], avoid=["course", "comments", "equiv", "approve"])
    if not name:
        for v in fd.values():
            if re.match(r"^[A-Za-z][A-Za-z .'-]+ [A-Za-z][A-Za-z .'-]+$", v):
                name = v
                break

    # Student ID
    student_id = pick_by_key(["student", "id"], value_re=r"^\d{5,10}$")
    if not student_id:
        for v in fd.values():
            if re.fullmatch(r"\d{5,10}", v or ""):
                student_id = v
                break

    # Class year
    class_year = pick_by_key(["class"], value_re=r"^\d{4}$")
    if not class_year:
        for v in fd.values():
            m = YEAR_RE.search(v or "")
            if m and len(v) <= 6:
                class_year = m.group(0)
                break

    # Date
    date_val = pick_by_key(["date"], value_re=DATE_RE.pattern)
    if not date_val:
        for v in fd.values():
            m = DATE_RE.search(v or "")
            if m:
                date_val = m.group(0)
                break

    # Program
    program = pick_by_key(
        ["college where", "study abroad", "program", "college"],
        avoid=["course", "comments", "equiv", "approve", "class", "semester", "id", "date", "name"]
    )
    if not program:
        candidates = []
        for k, v in fd.items():
            if not v:
                continue
            if any(bad in k for bad in ["course", "comments", "equiv", "approve", "majorminor", "class", "semester", "id", "date", "name"]):
                continue
            if re.search(
                r"(university|college|program|institute|ies|ciee|arcadia|barcelona|madrid|london|paris|florence|milan|prague)",
                v,
                re.I
            ):
                candidates.append(v)
        if candidates:
            program = max(candidates, key=len)

    # last resort: scan visible text for program-ish strings
    if not program:
        try:
            for block in page_blocks(pdf_bytes):
                text = block["text"].strip()
                if (
                    re.search(r"(ies abroad|ciee|university|college|program)", text, re.I)
                    and len(text) > 20
                    and not re.search(r"course|subject|number|title", text, re.I)
                ):
                    program = text
                    break
        except Exception:
            pass

    # Semester / Term
    semester = pick_by_key(["semester"], value_re=TERM_RE.pattern)
    if not semester:
        for v in fd.values():
            if TERM_RE.search(v or ""):
                semester = v
                break

    return {
        "Name": name,
        "StudentID": student_id,
        "ClassYear": class_year,
        "Date": date_val,
        "Program": program,
        "Semester": semester
    }

# ---------------- Signature detection helpers ----------------
def detect_visual_signatures_in_pdf(pdf_bytes: bytes, widgets: List[Dict]) -> Dict[str, bool]:
    """
    Attempt to detect ink-like marks / annotations in approval boxes.
    Returns map: {widget_name: bool}
    """
    signature_map = {}
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                drawings = page.get_drawings()
                annotations = list(page.annots()) if page.annots() else []

                for widget in widgets:
                    widget_name_full = widget.get("name", "")
                    widget_name = (widget_name_full or "").lower()
                    if widget["page"] != page_num:
                        continue
                    if not (
                        "elec" in widget_name or
                        "major" in widget_name or
                        "minor" in widget_name
                    ):
                        continue

                    rect = fitz.Rect(
                        widget["x0"] - 3, widget["y0"] - 3,
                        widget["x1"] + 3, widget["y1"] + 3
                    )

                    has_sig = False

                    # check drawings
                    for d in drawings:
                        for item in d.get("items", []):
                            # item[0] indicates shape type; item[1] may be geometry
                            if item[0] in [1, 2, 3]:  # line/rect/curve
                                if len(item) >= 2:
                                    geom = item[1]
                                    # rect intersection
                                    if hasattr(geom, "x0"):
                                        if rect.intersects(geom):
                                            has_sig = True
                                            break
                                    elif isinstance(geom, (list, tuple)) and len(geom) >= 2:
                                        x, y = geom[0], geom[1]
                                        if rect.x0 <= x <= rect.x1 and rect.y0 <= y <= rect.y1:
                                            has_sig = True
                                            break
                        if has_sig:
                            break

                    # check annotations
                    if not has_sig:
                        for annot in annotations:
                            if annot.rect.intersects(rect):
                                has_sig = True
                                break

                    # check text in that area
                    if not has_sig:
                        txt_clip = page.get_text("text", clip=rect)
                        if txt_clip.strip() and len(txt_clip.strip()) > 1:
                            has_sig = True

                    signature_map[widget_name_full] = has_sig

        return signature_map

    except Exception:
        # Fallback: all False
        for w in widgets:
            signature_map[w.get("name","")] = False
        return signature_map

# ---------------- Core row assembly ----------------
def build_rows(pdf_bytes: bytes) -> Tuple[pd.DataFrame, str, Dict[str,str]]:
    widgets, fields = read_form_widgets(pdf_bytes)
    header = infer_header_from_fields(fields, pdf_bytes)

    # small helper to gather widget values by suffix index
    def pick_widgets_containing(substring: str) -> List[Dict[str, Any]]:
        out = []
        for w in widgets:
            if substring.lower() in (w["name"] or "").lower():
                if w["value"]:
                    out.append({
                        "page": w["page"],
                        "y0": w["y0"],
                        "x0": w["x0"],
                        "value": w["value"]
                    })
        return out

    w_elec   = pick_widgets_containing("elecapprove")
    w_mm     = pick_widgets_containing("majorminorapproval")
    w_comm   = pick_widgets_containing("comments")
    w_equiv  = pick_widgets_containing("equivalent")
    # w_courses_form is not strictly used, but we keep the logic
    # to maintain the structure
    w_courses_form = pick_widgets_containing("course")

    # ---------- PATH A: structured "Course1 / Equivalent1 / ..." fields ----------
    rows_path_a: List[Dict[str, Any]] = []
    indices = set()

    for w in widgets:
        m = re.search(
            r"(course|equivalent|elecapprove|majorminorapproval|comments)\s*([0-9]+)$",
            (w["name"] or ""),
            re.I
        )
        if m:
            indices.add(int(m.group(2)))

    # detect visual signatures once at top (saves work per row)
    visual_signatures = detect_visual_signatures_in_pdf(pdf_bytes, widgets)

    for i in sorted(indices):
        raw_course = norm_space(fields.get(f"Course{i}", "") or fields.get(f"course{i}", ""))
        raw_equiv = norm_space(fields.get(f"Equivalent{i}", "") or fields.get(f"equivalent{i}", ""))
        raw_elec = norm_space(fields.get(f"ElecApprove{i}", "") or fields.get(f"elecapprove{i}", ""))
        raw_mm = norm_space(fields.get(f"MajorMinorApproval{i}", "") or fields.get(f"majorminorapproval{i}", ""))
        raw_comments = norm_space(fields.get(f"Comments{i}", "") or fields.get(f"comments{i}", ""))

        # If literally everything is empty, skip
        if not any([raw_course, raw_equiv, raw_elec, raw_mm, raw_comments]):
            continue

        course_code, course_title = parse_course_code_and_title(raw_course)
        ur_equivalent = raw_equiv  # <-- FIX: define so it's always available

        program_name, city, country = extract_program_info(header.get("Program", ""))

        # infer signature presence from visual_signatures for this index:
        signature_detected = {"elective": False, "major_minor": False}
        elec_widget_name = f"ElecApprove{i}"
        mm_widget_name = f"MajorMinorApproval{i}"

        if elec_widget_name in visual_signatures and visual_signatures[elec_widget_name]:
            signature_detected["elective"] = True
        if mm_widget_name in visual_signatures and visual_signatures[mm_widget_name]:
            signature_detected["major_minor"] = True

        approval_type = map_approval_type_from_signatures(
            signature_detected,
            raw_elec,
            raw_mm,
            raw_comments
        )

        rows_path_a.append({
            "Program/University": program_name,
            "City": city,
            "Country": country,
            "Course Code": course_code,
            "Course Title": course_title,
            "UR Equivalent": ur_equivalent,
            "Major/Minor or Elective": approval_type,
            "UR Credits": "",          # not captured here yet
            "Foreign Credits": "",     # not captured here yet
            "Course Page Link": "",    # not captured here yet
            "Syllabus Link": "",       # not captured here yet
            "CourseIndex": i,
            "Original_Course": raw_course,
            "Elective_Approval": raw_elec,
            "MajorMinor_Approval": raw_mm,
            "Comments": raw_comments
        })

    if rows_path_a:
        df_a = pd.DataFrame(rows_path_a).sort_values("CourseIndex")
        return df_a, "Form fields", header

    # ---------- PATH B: scrape visible text blocks and align by y ----------
    courses_text = extract_courses_by_blocks(pdf_bytes)
    assembled_b: List[Dict[str, Any]] = []

    for idx, c in enumerate(courses_text, start=1):
        # for each detected course line, find nearest data widgets
        near_eq  = nearest_by_y(c["y"], w_equiv, c["page"])
        near_el  = nearest_by_y(c["y"], w_elec,  c["page"])
        near_mm  = nearest_by_y(c["y"], w_mm,    c["page"])
        near_cm  = nearest_by_y(c["y"], w_comm,  c["page"])

        # parse course info
        course_code, course_title = parse_course_code_and_title(c["Course"])
        program_name, city, country = extract_program_info(header.get("Program", ""))

        # try to extract approval info from local block text (handwriting case)
        text_approval_data = extract_approval_data_from_text_blocks(pdf_bytes, c["y"], c["page"])

        # signature detection near row using widgets
        sig_detect_local = detect_signature_in_widgets(
            widgets,
            c["y"],
            c["page"]
        )

        # also factor in visual signatures
        if text_approval_data.get("elective"):
            sig_detect_local["elective"] = True
        if text_approval_data.get("major_minor"):
            sig_detect_local["major_minor"] = True

        # pick final approval fields
        elective_approval = (near_el or {}).get("value", "") or text_approval_data.get("elective", "")
        major_minor_approval = (near_mm or {}).get("value", "") or text_approval_data.get("major_minor", "")
        comments = (near_cm or {}).get("value", "") or text_approval_data.get("comments", "")

        ur_equivalent = (
            (near_eq or {}).get("value", "") or
            text_approval_data.get("ur_equivalent", "")
        )

        approval_type = map_approval_type_from_signatures(
            sig_detect_local,
            elective_approval,
            major_minor_approval,
            comments
        )

        assembled_b.append({
            "Program/University": program_name,
            "City": city,
            "Country": country,
            "Course Code": course_code,
            "Course Title": course_title,
            "UR Equivalent": ur_equivalent,
            "Major/Minor or Elective": approval_type,
            "UR Credits": "",
            "Foreign Credits": "",
            "Course Page Link": "",
            "Syllabus Link": "",
            "CourseIndex": idx,
            "Original_Course": c["Course"],
            "Elective_Approval": elective_approval,
            "MajorMinor_Approval": major_minor_approval,
            "Comments": comments,
            "Debug_Signature_Detected": str(sig_detect_local),
            "Debug_Course_Y": c["y"],
        })

    if assembled_b:
        df_b = pd.DataFrame(assembled_b)
        df_b = df_b[df_b["Original_Course"].str.strip().ne("")]
        return df_b, "Text blocks (y-aligned)", header

    # ---------- PATH C: OCR fallback ----------
    ocr_txt = ocr_text(pdf_bytes, dpi=300)
    lines = []
    exclude_patterns = [
        r"^THE\s+COLLEGE",
        r"^COURSE\s+APPROVAL",
        r"^IES\s+Abroad",
        r"^DEPARTMENT\s+OR\s+OFFICE",
        r"^STUDENTS\s+Complete",
        r"^AUTHORIZED\s+APPROVERS",
        r"^HOW\s+TO\s+TRANSFER",
        r"^FORM\s*$",
        r"^APPROVAL\s*$",
        r"^COLLEGE\s*$",
        r"^COURSE\s*$"
    ]
    for l in ocr_txt.splitlines():
        line_clean = l.strip()
        if COURSE_LINE_RE.match(line_clean):
            skip = False
            for patt in exclude_patterns:
                if re.match(patt, line_clean, re.I):
                    skip = True
                    break
            if not skip:
                lines.append(l)

    if lines:
        assembled_c = []
        for i, l in enumerate(lines, start=1):
            course_text = clean_course_text(l)
            code_c, title_c = parse_course_code_and_title(course_text)
            program_name, city, country = extract_program_info(header.get("Program", ""))

            assembled_c.append({
                "Program/University": program_name,
                "City": city,
                "Country": country,
                "Course Code": code_c,
                "Course Title": title_c,
                "UR Equivalent": "",
                "Major/Minor or Elective": "",
                "UR Credits": "",
                "Foreign Credits": "",
                "Course Page Link": "",
                "Syllabus Link": "",
                "CourseIndex": i,
                "Original_Course": course_text,
                "Elective_Approval": "",
                "MajorMinor_Approval": "",
                "Comments": ""
            })

        df_c = pd.DataFrame(assembled_c)
        return df_c, "OCR (courses only)", header

    # If literally nothing worked:
    return pd.DataFrame(), "None", header

# ---------------- Streamlit UI ----------------
st.sidebar.header("Upload Options")
upload_mode = st.sidebar.radio("Choose upload mode:", ["Single File", "Bulk Upload"])

if upload_mode == "Single File":
    upl = st.file_uploader("Upload CAF PDF", type=["pdf"])
    if not upl:
        st.info("Upload a PDF to begin.")
        st.stop()
    pdf_files = [upl]
    file_names = [upl.name]
else:
    upl = st.file_uploader("Upload multiple CAF PDFs", type=["pdf"], accept_multiple_files=True)
    if not upl:
        st.info("Upload one or more PDFs to begin.")
        st.stop()
    pdf_files = upl
    file_names = [f.name for f in upl]

all_results = []
all_headers = []

for pdf_file, file_name in zip(pdf_files, file_names):
    st.write(f"Processing {file_name}...")
    pdf_bytes = pdf_file.read()

    with st.spinner(f"Parsing {file_name}..."):
        df, path, header = build_rows(pdf_bytes)

    if not df.empty:
        df["Source File"] = file_name
        all_results.append(df)
        all_headers.append(header)
        st.success(f"✓ {file_name}: {len(df)} course(s) extracted via **{path}**")
    else:
        st.warning(f"⚠ {file_name}: No courses detected")

# Combine
if all_results:
    combined_df = pd.concat(all_results, ignore_index=True)
    st.subheader(f"Combined Results ({len(combined_df)} total courses from {len(all_results)} file(s))")
else:
    combined_df = pd.DataFrame()
    st.error("No courses detected from any files.")

# Display
if combined_df.empty:
    st.error("No courses detected from any files. Try clearer scans or different files.")
else:
    desired_cols = [
        "Source File",
        "Program/University",
        "City",
        "Country",
        "Course Code",
        "Course Title",
        "UR Equivalent",
        "Major/Minor or Elective",
        "UR Credits",
        "Foreign Credits",
        "Course Page Link",
        "Syllabus Link"
    ]

    # Ensure all columns exist
    for col in desired_cols:
        if col not in combined_df.columns:
            combined_df[col] = ""

    final_df = combined_df[desired_cols].copy()

    st.dataframe(final_df, use_container_width=True)

    csv_data = final_df.to_csv(index=False)
    st.download_button(
        "Download Combined Results as CSV",
        csv_data.encode("utf-8"),
        file_name="caf_bulk_results.csv",
        mime="text/csv"
    )

    # Debug info
    with st.expander("Debug: Original Data"):
        st.dataframe(combined_df, use_container_width=True)

    with st.expander("Debug: Signature Detection Details"):
        widgets, fields = read_form_widgets(pdf_bytes)

        st.write("**All Widgets Found:**")
        all_widgets = []
        for w in widgets:
            all_widgets.append({
                "Widget Name": w["name"],
                "Value": w["value"],
                "Page": w["page"],
                "Y Position": round(w["y0"], 1)
            })
        if all_widgets:
            st.dataframe(pd.DataFrame(all_widgets), use_container_width=True)
        else:
            st.write("No widgets found at all.")

        st.write("**Approval Widgets (text-based signature guess):**")
        sig_rows = []
        for w in widgets:
            widget_name = (w["name"] or "").lower()
            widget_value = (w["value"] or "").strip()
            is_approval_widget = (
                "elec" in widget_name or
                "major" in widget_name or
                "minor" in widget_name
            )
            if is_approval_widget:
                # if looks like real initials/name (not generic yes/no)
                has_signature = (
                    widget_value
                    and widget_value.lower() not in
                    ["", "no", "n", "none", "yes", "y", "approved", "denied"]
                    and len(widget_value.strip()) > 1
                )
                sig_rows.append({
                    "Widget Name": w["name"],
                    "Value": widget_value,
                    "Page": w["page"],
                    "Y Position": round(w["y0"], 1),
                    "Type": "Elective" if "elec" in widget_name else "Major/Minor",
                    "Has Signature (text)": has_signature
                })
        if sig_rows:
            st.dataframe(pd.DataFrame(sig_rows), use_container_width=True)
        else:
            st.write("No approval widgets found.")

        st.write("**Visual Signature Detection Results:**")
        vis_map = detect_visual_signatures_in_pdf(pdf_bytes, widgets)
        vis_rows = []
        for widget_name, has_sig in vis_map.items():
            low = widget_name.lower() if widget_name else ""
            if "elec" in low or "major" in low or "minor" in low:
                vis_rows.append({
                    "Widget Name": widget_name,
                    "Has Visual Signature": has_sig
                })
        if vis_rows:
            st.dataframe(pd.DataFrame(vis_rows), use_container_width=True)
        else:
            st.write("No visual signatures detected.")

with st.expander("Debug: Header & Raw Form Fields"):
    # NOTE: pdf_bytes will be last processed file's bytes
    st.write("Header inference:", all_headers[-1] if all_headers else {})
    if 'pdf_bytes' in locals():
        widgets, fields = read_form_widgets(pdf_bytes)
        st.write("Raw field keys (sample):", list(fields.keys())[:50])
    else:
        st.write("No file processed.")
