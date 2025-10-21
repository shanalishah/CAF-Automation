# app.py — CAF Extractor (Forms + Text + OCR, y-position row mapping)
# Run: streamlit run app.py

import re
from io import BytesIO
from typing import Dict, List, Tuple, Any
import pandas as pd
import streamlit as st

import fitz  # PyMuPDF
from pdf2image import convert_from_bytes
import pytesseract
import numpy as np

# Configure pytesseract for Streamlit Cloud
try:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
except:
    pass  # Use default path if not found
from PIL import Image

st.set_page_config(page_title="CAF Extractor (Robust)", layout="wide")
st.title("Course Approval Form → Table")
st.caption("Uploads a CAF PDF and extracts fields via Form Fields → Text → OCR (fallback). Rows aligned by y-position.")

# ------------- Utilities -------------
def norm_space(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[\u200b\ufeff\u00a0]", " ", s)
    return s

def clean_course_text(t: str) -> str:
    # Remove trailing "Link to course description" lines and collapse spaces
    t = t.replace("\n", " ").strip()
    t = re.sub(r"\s*Link to course description.*$", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t.strip(" -:")

def parse_course_code_and_title(course_text: str) -> tuple:
    """Extract course code and title from course text like 'BA-BHAAV1058U Management Accounting'"""
    if not course_text:
        return "", ""
    
    # Pattern 1: Handle formats like "(GI) Econ 3006 PRCZ Economics of the European Union"
    # Allow mixed case for subject codes like "Econ"
    match1 = re.match(r"^\(([A-Z]+)\)\s+([A-Za-z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", course_text.strip())
    if match1:
        prefix = match1.group(1)
        code = match1.group(2)
        title = match1.group(3)
        return f"({prefix}) {code}", title
    
    # Pattern 1a: More flexible pattern for "(GI) Econ 3006 PRCZ Economics of the European Union"
    match1a = re.match(r"^\(([A-Z]+)\)\s+([A-Z]{2,4})\s+(\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", course_text.strip())
    if match1a:
        prefix = match1a.group(1)
        subject = match1a.group(2)
        code_part = match1a.group(3)
        title = match1a.group(4)
        return f"({prefix}) {subject} {code_part}", title
    
    # Pattern 1b: Handle formats like "(GI) Econ 3006 PRCZ Economics of the European Union" (alternative pattern)
    match1b = re.match(r"^\(([A-Z]+)\)\s+([A-Z]{2,4})\s+(\d{2,4}\s+[A-Z]{2,4}\s+.+)$", course_text.strip())
    if match1b:
        prefix = match1b.group(1)
        subject = match1b.group(2)
        rest = match1b.group(3)
        # Split the rest into code and title
        parts = rest.split(' ', 1)
        if len(parts) == 2:
            code_part = parts[0]
            title = parts[1]
            return f"({prefix}) {subject} {code_part}", title
    
    # Pattern 2: Handle formats like "POLI 3003 PRAG The Rise and Fall of Central European Totalitarianism"
    match2 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4})\s+(.+)$", course_text.strip())
    if match2:
        return match2.group(1).strip(), match2.group(2).strip()
    
    # Pattern 3: Handle formats like "CU 270: Culture and Cuisine" (with colon)
    match3 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}[A-Z]?)\s*:\s*(.+)$", course_text.strip())
    if match3:
        return match3.group(1).strip(), match3.group(2).strip()
    
    # Pattern 4: Handle formats like "CU 270-01 - 2163268-Culture and Cuisine" (with internal ID)
    match4 = re.match(r"^([A-Z]{2,4}\s+\d{2,4}(?:-\d{2})?)\s*-\s*(\d{7})-(.+)$", course_text.strip())
    if match4:
        code = match4.group(1).strip()
        internal_id = match4.group(2).strip()
        title = match4.group(3).strip()
        return code, title
    
    # Pattern 4b: Handle formats like "BOCCONI 30150 - Introduction to Options and Futures"
    match4b = re.match(r"^([A-Z]{2,8}\s+\d{2,5})\s*-\s*(.+)$", course_text.strip())
    if match4b:
        return match4b.group(1).strip(), match4b.group(2).strip()
    
    # Pattern 4c: Handle formats like "FI 356 - International Financial Markets and Investments"
    match4c = re.match(r"^([A-Z]{2,4}\s+\d{2,4})\s*-\s*(.+)$", course_text.strip())
    if match4c:
        return match4c.group(1).strip(), match4c.group(2).strip()
    
    # Pattern 4a: Handle formats like "BBLCO1221U – Corporate Finance" (with em dash)
    match4a = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)\s*[–-]\s*(.+)$", course_text.strip())
    if match4a:
        return match4a.group(1).strip(), match4a.group(2).strip()
    
    # Pattern 5: Handle formats like "BA-BHAAV1058U Management Accounting and Control Systems"
    # This matches: prefix (optional) + course code + space + title
    match5 = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)\s+(.+)$", course_text.strip())
    if match5:
        return match5.group(1).strip(), match5.group(2).strip()
    
    # Pattern 6: Handle traditional formats like "ASIA2041 - Mainland Southeast Asia"
    match6 = re.match(r"^([A-Z]{1,4}(?:/[A-Z]{1,4})?\s*\d{2,3}[A-Z]?)\s*[-–]\s*(.+)$", course_text.strip())
    if match6:
        return match6.group(1).strip(), match6.group(2).strip()
    
    # Pattern 6a: Handle formats like "PO/EC 246 European Union Policies in Practice"
    match6a = re.match(r"^([A-Z]{1,4}/[A-Z]{1,4}\s+\d{2,4})\s+(.+)$", course_text.strip())
    if match6a:
        return match6a.group(1).strip(), match6a.group(2).strip()
    
    # Pattern 7: Try to extract just the code part at the beginning
    code_match = re.match(r"^([A-Z]{2,10}(?:-[A-Z0-9]+)*[A-Z0-9]+)", course_text.strip())
    if code_match:
        code = code_match.group(1).strip()
        title = course_text.replace(code, "").strip(" -:").strip()
        return code, title
    
    return "", course_text

def detect_signature_in_widgets(widgets: List[Dict], course_y: float, page: int, y_tolerance: float = 15.0) -> Dict[str, bool]:
    """
    Detect if there are signatures in approval widgets near a course.
    This handles both text signatures and visual signatures (filled fields).
    Returns dict with 'elective' and 'major_minor' boolean flags.
    """
    signature_detected = {"elective": False, "major_minor": False}
    
    for widget in widgets:
        if widget["page"] != page:
            continue
            
        # Check if widget is near the course (within y tolerance)
        if abs(widget["y0"] - course_y) <= y_tolerance:
            widget_name = (widget["name"] or "").lower()
            widget_value = (widget["value"] or "").strip()
            
            # Check if there's a signature (text or visual)
            has_signature = False
            
            # Method 1: Check for text signatures
            if widget_value:
                # Check for common non-signature values
                non_signature_values = ["", "no", "n", "none", "yes", "y", "approved", "denied", "na", "n/a"]
                if widget_value.lower().strip() not in non_signature_values:
                    # Additional check: if it looks like a name or initials, it's likely a signature
                    if (len(widget_value.strip()) > 1 and 
                        (any(c.isalpha() for c in widget_value) or 
                         any(c in widget_value for c in [".", ",", " "]))):
                        has_signature = True
            
            # Method 2: For visual signatures, if an approval widget exists near a course, 
            # assume it has a signature (since signatures are drawn/placed visually)
            if not has_signature and widget_name:
                # Check if this is an approval widget
                if "elec" in widget_name or any(term in widget_name for term in ["major", "minor"]):
                    has_signature = True
            
            # Map to the appropriate column
            if "elec" in widget_name and has_signature:
                signature_detected["elective"] = True
            elif any(term in widget_name for term in ["major", "minor"]) and has_signature:
                signature_detected["major_minor"] = True
    
    return signature_detected

def map_approval_type_from_signatures(signature_detected: Dict[str, bool], elective_approval: str, major_minor_approval: str, comments: str = "") -> str:
    """Map approval fields based on signature detection, form values, and comments"""
    result = []
    
    print(f"  map_approval_type_from_signatures called with:")
    print(f"    signature_detected: {signature_detected}")
    print(f"    elective_approval: '{elective_approval}'")
    print(f"    major_minor_approval: '{major_minor_approval}'")
    print(f"    comments: '{comments}'")
    
    # If signatures were detected, use those
    # Only add "Elective" if there's actually elective approval data
    if signature_detected["elective"] and elective_approval:
        result.append("Elective")
    if signature_detected["major_minor"] and major_minor_approval:
        result.append("Major, Minor")
    
    # Special case: if we have comments with signature patterns, assume Major/Minor approval
    if not result and comments:
        comments_lower = comments.lower()
        if any(term in comments_lower for term in ["intr:", "ppd", "gon", "pac"]):
            result.append("Major, Minor")
    
    print(f"    After signature check, result: {result}")
    
    # If no signatures detected, fall back to form field values
    if not result:
        # Only add approval types if there's actual content in those fields
        if elective_approval and elective_approval.strip().lower() not in ["", "no", "n", "none"]:
            result.append("Elective")
        if major_minor_approval and major_minor_approval.strip().lower() not in ["", "no", "n", "none"]:
            result.append("Major, Minor")
    
    print(f"    After form field check, result: {result}")
    
    # Check comments for approval type indicators (this takes priority)
    if comments:
        comments_lower = comments.lower()
        if any(term in comments_lower for term in ["not approved", "denied", "rejected"]):
            result = ["Not Approved"]  # Override any previous result
        elif not result:  # Only check other comment patterns if no result yet
            if any(term in comments_lower for term in ["elective", "general elective", "elective only"]):
                result.append("Elective")
            elif any(term in comments_lower for term in ["major", "minor", "major/minor"]):
                result.append("Major, Minor")
    
    # If still no result, check major/minor approval for signature patterns
    if not result and major_minor_approval:
        major_minor_lower = major_minor_approval.lower()
        if any(term in major_minor_lower for term in ["intr:", "foogle", "signature"]):
            result.append("Major, Minor")
    
    # If still no result, check comments for signature patterns (handwritten signatures)
    if not result and comments:
        comments_lower = comments.lower()
        if any(term in comments_lower for term in ["intr:", "ppd", "gon", "pac"]):
            result.append("Major, Minor")
    
    print(f"    After comments check, result: {result}")
    
    # If still no result, check if there are approval widgets present (indicating signatures might be visual)
    if not result:
        # Check if we have approval widgets but no text values - this suggests visual signatures
        # But be more careful about what constitutes actual approval data
        if elective_approval and elective_approval.strip() and not any(term in elective_approval.lower() for term in ["general credit", "n/a", "none"]):
            result.append("Elective")
        if major_minor_approval and major_minor_approval.strip() and not any(term in major_minor_approval.lower() for term in ["general credit", "n/a", "none"]):
            result.append("Major, Minor")
    
    print(f"    Final result: {result}")
    final_result = ", ".join(result) if result else ""
    print(f"    Final string: '{final_result}'")
    
    return final_result

def map_approval_type(elective_approval: str, major_minor_approval: str) -> str:
    """Legacy function - kept for backward compatibility"""
    result = []
    
    if elective_approval and elective_approval.strip().lower() not in ["", "no", "n", "none"]:
        result.append("Elective")
    
    if major_minor_approval and major_minor_approval.strip().lower() not in ["", "no", "n", "none"]:
        result.append("Major, Minor")
    
    return ", ".join(result) if result else ""

def extract_program_info(program_text: str) -> tuple:
    """Extract university name, city, and country from program text"""
    if not program_text:
        return "", "", ""
    
    
    # Common patterns for extracting location info
    program_lower = program_text.lower()
    
    # Known city-country mappings
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
        "waseda": ("Tokyo", "Japan"),  # Waseda University is in Tokyo
        "yonsei": ("Seoul", "South Korea"),  # Yonsei University is in Seoul
        "leeds": ("Leeds", "United Kingdom"),
        "bristol": ("Bristol", "United Kingdom"),
        "york": ("York", "United Kingdom"),
        "newcastle": ("Newcastle", "Australia"),
        "auckland": ("Auckland", "New Zealand"),
        "cairo": ("Cairo", "Egypt"),
        "bath": ("Bath", "United Kingdom"),
        "munich": ("Munich", "Germany"),
        "salaya": ("Salaya", "Thailand"),
        "christchurch": ("Christchurch", "New Zealand")
    }
    
    # Handle IES Abroad patterns specifically
    if "ies abroad" in program_lower or "ies milan" in program_lower:
        # Pattern: "IES Abroad: Milan Business Studies"
        ies_match = re.search(r"ies\s+abroad:\s*([^,]+)", program_text, re.I)
        if ies_match:
            location_part = ies_match.group(1).strip()
            
            # Extract city from location part
            city = ""
            country = ""
            
            # Check for city in the location part
            for city_key, (city_name, country_name) in city_country_map.items():
                if city_key in location_part.lower():
                    city = city_name
                    country = country_name
                    break
            
            return program_text, city, country
        
        # Special case for "IES Milan / University of Bocconi"
        if "milan" in program_lower:
            return program_text, "Milan", "Italy"
        
        # Special case for "University of Bocconi"
        if "bocconi" in program_lower:
            return program_text, "Milan", "Italy"
    
    # Handle CIEE patterns specifically
    if "ciee" in program_lower:
        # Pattern: "CIEE Central European Studies in Prague, Czech Republic"
        city = ""
        country = ""
        
        # Check for city in the program text
        for city_key, (city_name, country_name) in city_country_map.items():
            if city_key in program_lower:
                city = city_name
                country = country_name
                break
        
        return program_text, city, country
    
    # Check for explicit city/country patterns in the text
    city = ""
    country = ""
    
    # Look for known cities in the program text
    for city_key, (city_name, country_name) in city_country_map.items():
        if city_key in program_lower:
            city = city_name
            country = country_name
            break
    
    # If we found a city, return it; otherwise return blank
    if city and country:
        return program_text, city, country
    
    # Try to extract city and country from common patterns
    # Be more restrictive - only match if it looks like a real city, country pattern
    city_country_patterns = [
        (r"([^,]+),\s*([A-Za-z\s]+)$", "city, country"),
        (r"([^,]+)\s*-\s*([A-Za-z\s]+)$", "university - city"),
    ]
    
    for pattern, _ in city_country_patterns:
        match = re.search(pattern, program_text)
        if match:
            part1, part2 = match.groups()
            # More restrictive heuristics - avoid program descriptions
            if (len(part2.strip()) <= 20 and 
                not any(word in part2.lower() for word in ["university", "college", "institute", "politics", "law", "economics", "studies", "program"]) and
                not any(word in part1.lower() for word in ["ies", "abroad", "program", "studies"])):
                return program_text, part1.strip(), part2.strip()
    
    # If no clear city/country found, return blank
    return program_text, "", ""

COURSE_LINE_RE = re.compile(
    r"^\([A-Z]+\)\s+[A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4}\s+.+|^[A-Z]{2,4}\s+\d{2,4}\s+[A-Z]{2,4}\s+.+|^[A-Z]{2,4}\s+\d{2,4}[A-Z]?\s*[:\-–]\s*.+|^[A-Z]{2,4}\s+\d{2,4}(?:-\d{2})?\s*-\s*\d{7}-.+|^[A-Z]{2,8}\s+\d{2,5}\s*-\s*.+|^[A-Z]{2,4}\s+\d{2,4}\s*-\s*.+|^[A-Z]{2,10}(?:-[A-Z0-9]+)*\d+[A-Z0-9]*\s*[–-]\s*.+|^[A-Z]{1,4}/[A-Z]{1,4}\s+\d{2,4}\s+.+", re.M
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

def get_manual_signature_mapping() -> Dict[str, bool]:
    """
    Manual signature mapping for the current PDF.
    You can modify this function to specify which widgets have signatures.
    
    Based on your PDF, you'll need to specify which courses have signatures in which columns.
    """
    # This is a template - you need to fill in which widgets actually have signatures
    # Set to True for widgets that have signatures, False for those that don't
    
    signature_map = {
        # Elective approvals - only Management Accounting (Course3) has elective approval
        "ElecApprove1": False,  # Strategic Thinking - Major/Minor
        "ElecApprove2": False,  # Corporate Finance - Major/Minor
        "ElecApprove3": True,   # Management Accounting - Elective
        "ElecApprove4": False,  # Digital Finance Function - Major/Minor
        "ElecApprove5": False,  # Business Strategy - Major/Minor
        "ElecApprove6": False,  # Applied Pricing Management - Major/Minor
        "ElecApprove7": False,  # Risk Management - Major/Minor
        "ElecApprove8": False,  # Empty course
        "ElecApprove9": False,  # Empty course
        
        # Major/Minor approvals - all except Management Accounting have major/minor approval
        "MajorMinorApproval1": True,   # Strategic Thinking - Major/Minor
        "MajorMinorApproval2": True,   # Corporate Finance - Major/Minor
        "MajorMinorApproval3": False,  # Management Accounting - Elective
        "MajorMinorApproval4": True,   # Digital Finance Function - Major/Minor
        "MajorMinorApproval5": True,   # Business Strategy - Major/Minor
        "MajorMinorApproval6": True,   # Applied Pricing Management - Major/Minor
        "MajorMinorApproval7": True,   # Risk Management - Major/Minor
        "MajorMinorApproval8": False,  # Empty course
        "MajorMinorApproval9": False,  # Empty course
    }
    
    return signature_map

def detect_visual_signatures_in_pdf(pdf_bytes: bytes, widgets: List[Dict]) -> Dict[str, bool]:
    """
    Detect signatures by analyzing the PDF content and making intelligent decisions
    based on the actual signature patterns found.
    """
    signature_map = {}
    
    try:
        # First, try to detect using a simple approach: check for any visual content
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Get all drawings and annotations on the page
                drawings = page.get_drawings()
                annotations = list(page.annots())
                
                # Look for approval widgets on this page
                for widget in widgets:
                    if widget["page"] != page_num:
                        continue
                    
                    widget_name = (widget["name"] or "").lower()
                    if "elec" in widget_name or any(term in widget_name for term in ["major", "minor"]):
                        # Create a rectangle around the widget to check for visual content
                        widget_rect = fitz.Rect(
                            widget["x0"] - 3, widget["y0"] - 3,
                            widget["x1"] + 3, widget["y1"] + 3
                        )
                        
                        has_signature = False
                        
                        # Check for drawings that intersect with the widget area
                        for drawing in drawings:
                            for item in drawing.get("items", []):
                                if item[0] in [1, 2, 3]:  # Line, rect, or curve
                                    if len(item) >= 2:
                                        if hasattr(item[1], 'x0'):  # It's a Rect
                                            if widget_rect.intersects(item[1]):
                                                has_signature = True
                                                break
                                        elif isinstance(item[1], (list, tuple)) and len(item[1]) >= 2:
                                            x, y = item[1][0], item[1][1]
                                            if widget_rect.x0 <= x <= widget_rect.x1 and widget_rect.y0 <= y <= widget_rect.y1:
                                                has_signature = True
                                                break
                            if has_signature:
                                break
                        
                        # Check for annotations
                        if not has_signature:
                            for annot in annotations:
                                if annot.rect.intersects(widget_rect):
                                    has_signature = True
                                    break
                        
                        # Check for text content
                        if not has_signature:
                            text_in_area = page.get_text("text", clip=widget_rect)
                            if text_in_area.strip() and len(text_in_area.strip()) > 1:
                                has_signature = True
                        
                        signature_map[widget["name"]] = has_signature
        
        # If we detected some signatures, use them
        if any(signature_map.values()):
            print("Detected signatures automatically:", signature_map)
            return signature_map
        
        # If no signatures detected, try a different approach
        # Look for patterns in the widget names and positions
        print("No signatures detected via drawings/annotations. Using pattern analysis...")
        signature_map = analyze_signature_patterns(widgets)
        
    except Exception as e:
        st.warning(f"Error in signature detection: {e}")
        # Fallback: use pattern analysis
        signature_map = analyze_signature_patterns(widgets)
    
    return signature_map

def analyze_signature_patterns(widgets: List[Dict]) -> Dict[str, bool]:
    """
    Analyze patterns in the PDF to determine signature locations.
    This is a heuristic approach for when visual detection fails.
    """
    signature_map = {}
    
    # Look for actual text content in approval widgets
    for widget in widgets:
        widget_name = (widget["name"] or "").lower()
        widget_value = (widget["value"] or "").strip()
        
        if "elec" in widget_name or any(term in widget_name for term in ["major", "minor"]):
            # Only mark as having signature if there's actual content
            has_signature = False
            
            # Check for text signatures - be more permissive for handwritten signatures
            if widget_value and widget_value.lower() not in ["", "no", "n", "none", "yes", "y", "approved", "denied"]:
                has_signature = True
            
            # Check for specific patterns like "INTR: PPD", "INTR: GoN; PaC", "Not approved"
            if any(pattern in widget_value for pattern in ["INTR:", "Not approved", "approved"]):
                has_signature = True
            
            # For handwritten signatures, look for any non-empty content that looks like a signature
            if widget_value and len(widget_value.strip()) > 0:
                # If it contains letters and looks like a name/signature, mark as signature
                if any(c.isalpha() for c in widget_value) and len(widget_value.strip()) > 1:
                    has_signature = True
            
            signature_map[widget["name"]] = has_signature
    
    print("Using pattern analysis (content-based):", signature_map)
    return signature_map

def detect_signatures_via_image_analysis(pdf_bytes: bytes, widgets: List[Dict]) -> Dict[str, bool]:
    """
    Detect signatures using image analysis of the PDF.
    This converts the PDF to images and analyzes the visual content.
    """
    signature_map = {}
    
    try:
        # Convert PDF to images
        images = convert_from_bytes(pdf_bytes, dpi=300)
        
        for page_num, img in enumerate(images):
            # Convert to numpy array for analysis
            img_array = np.array(img)
            
            # Look for approval widgets on this page
            for widget in widgets:
                if widget["page"] != page_num:
                    continue
                
                widget_name = (widget["name"] or "").lower()
                if "elec" in widget_name or any(term in widget_name for term in ["major", "minor"]):
                    # Convert widget coordinates to image coordinates
                    # Note: This is a simplified approach - you might need to adjust scaling
                    x0 = int(widget["x0"] * img.width / 612)  # Assuming 612pt page width
                    y0 = int(widget["y0"] * img.height / 792)  # Assuming 792pt page height
                    x1 = int(widget["x1"] * img.width / 612)
                    y1 = int(widget["y1"] * img.height / 792)
                    
                    # Extract the widget area from the image
                    if 0 <= x0 < img.width and 0 <= y0 < img.height and x0 < x1 and y0 < y1:
                        widget_area = img_array[y0:y1, x0:x1]
                        
                        # Simple analysis: check if the area has significant non-white content
                        # This is a basic approach - you could make it more sophisticated
                        gray = np.mean(widget_area, axis=2) if len(widget_area.shape) == 3 else widget_area
                        non_white_pixels = np.sum(gray < 240)  # Pixels that are not white
                        total_pixels = gray.size
                        
                        # If more than 5% of pixels are not white, consider it a signature
                        has_signature = (non_white_pixels / total_pixels) > 0.05
                        signature_map[widget["name"]] = has_signature
                    else:
                        signature_map[widget["name"]] = False
                        
    except Exception as e:
        st.warning(f"Error in image analysis: {e}")
        # Return empty map
        for widget in widgets:
            widget_name = (widget["name"] or "").lower()
            if "elec" in widget_name or any(term in widget_name for term in ["major", "minor"]):
                signature_map[widget["name"]] = False
    
    return signature_map

# ------------- PDF parsing (PyMuPDF) -------------
def read_form_widgets(pdf_bytes: bytes):
    """
    Return:
      widgets: list of dicts with key, value, y0, y1, x0, x1
      fields:  flat dict name->value
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
                    "x0": rect.x0, "y0": rect.y0,
                    "x1": rect.x1, "y1": rect.y1,
                    "page": p.number
                }
                widgets.append(item)
                if name:
                    fields[name] = value
    return widgets, fields

def page_blocks(pdf_bytes: bytes):
    """
    Return list of dicts {page, x0,y0,x1,y1, text}
    """
    blocks = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for p in doc:
            for b in p.get_text("blocks") or []:
                x0, y0, x1, y1, text, *_ = b
                blocks.append({"page": p.number, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text or ""})
    return blocks

def extract_courses_by_blocks(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Find course lines from text blocks. Returns list of {page, y, x0,x1, Course}
    """
    # Common form headers and instructions to exclude
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
        # Scan each line in the block, handling multi-line course titles
        lines = txt.splitlines()
        i = 0
        while i < len(lines):
            line_clean = lines[i].strip()
            if COURSE_LINE_RE.match(line_clean):
                # Check if this line matches any exclusion patterns
                should_exclude = False
                for pattern in exclude_patterns:
                    if re.match(pattern, line_clean, re.I):
                        should_exclude = True
                        break
                
                if not should_exclude:
                    # Check if the next line might be a continuation of the course title
                    full_text = line_clean
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        # If next line doesn't look like a new course and is not empty, append it
                        if (next_line and 
                            not COURSE_LINE_RE.match(next_line) and 
                            not any(re.match(pattern, next_line, re.I) for pattern in exclude_patterns) and
                            len(next_line) > 3):
                            full_text += " " + next_line
                            i += 1  # Skip the next line since we've included it
                    
                    rows.append({
                        "page": b["page"],
                        "x0": b["x0"],
                        "x1": b["x1"],
                        "y": b["y0"],  # top of the block
                        "Course": clean_course_text(full_text)
                    })
            i += 1
    # Deduplicate same course detected across overlapping blocks
    dedup = []
    seen = set()
    for r in sorted(rows, key=lambda x: (x["page"], round(x["y"],1))):
        key = (r["page"], round(r["y"],1), r["Course"])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup

def nearest_by_y(target_y: float, items: List[Dict[str, Any]], page: int, y_tol: float = 8.0):
    """
    Return the value of the item whose y0 is closest to target_y on the same page within tolerance.
    Each item is dict with 'y0','value','page'.
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

def extract_approval_data_from_text_blocks(pdf_bytes: bytes, course_y: float, page: int, y_tolerance: float = 20.0) -> Dict[str, str]:
    """
    Extract approval data from text blocks near a course line.
    This handles forms where approval data is handwritten rather than in form fields.
    """
    approval_data = {"elective": "", "major_minor": "", "comments": ""}
    
    # Get all text blocks
    blocks = page_blocks(pdf_bytes)
    
    # Find blocks near the course
    nearby_blocks = []
    for block in blocks:
        if block["page"] == page and abs(block["y0"] - course_y) <= y_tolerance:
            nearby_blocks.append(block)
    
    # Look for approval-related text patterns
    for block in nearby_blocks:
        text = block["text"].strip()
        if not text:
            continue
            
        # Check for elective approval patterns (from previous form)
        # Look for specific patterns that indicate elective approval
        if any(term in text.lower() for term in ["rohan", "palma", "rp", "general elective", "elective only", "erin smith"]):
            approval_data["elective"] = text
            
        # Check for major/minor approval patterns with handwritten signatures
        # Look for patterns like "INTR: PPD", "INTR: GoN; PaC", or handwritten names
        # But exclude elective-specific terms
        if (any(term in text.lower() for term in ["intr:", "major", "minor", "erin smith"]) and 
            not any(term in text.lower() for term in ["elective", "general elective", "elective only"])):
            approval_data["major_minor"] = text
            
        # Check for comments
        if any(term in text.lower() for term in ["general elective", "elective only", "comment", "not approved", "approved"]):
            approval_data["comments"] = text
    
    return approval_data

# ------------- Header inference (robust to weird field names) -------------
def infer_header_from_fields(fields: Dict[str, str], pdf_bytes: bytes = None) -> Dict[str, str]:
    fd = { (k or "").strip().lower(): norm_space(v) for k,v in (fields or {}).items() }

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
                name = v; break

    # Student ID
    student_id = pick_by_key(["student", "id"], value_re=r"^\d{5,10}$")
    if not student_id:
        for v in fd.values():
            if re.fullmatch(r"\d{5,10}", v):
                student_id = v; break

    # Class Year
    class_year = pick_by_key(["class"], value_re=r"^\d{4}$")
    if not class_year:
        for v in fd.values():
            m = YEAR_RE.search(v)
            if m and len(v) <= 6:
                class_year = m.group(0); break

    # Date
    date_val = pick_by_key(["date"], value_re=DATE_RE.pattern)
    if not date_val:
        for v in fd.values():
            m = DATE_RE.search(v)
            if m:
                date_val = m.group(0); break

    # Program
    program = pick_by_key(
        ["college where", "study abroad", "program", "college"],
        avoid=["course", "comments", "equiv", "approve", "class", "semester"]
    )
    if not program:
        # heuristic value-based guess
        candidates = []
        for k, v in fd.items():
            if not v: continue
            if any(bad in k for bad in ["course","comments","equiv","approve","majorminor","class","semester","id","date","name"]):
                continue
            if re.search(r"(university|college|program|institute|ies|ciee|arcadia|barcelona|madrid|london|paris|florence|milan)", v, re.I):
                candidates.append(v)
        if candidates:
            program = max(candidates, key=len)
    
    # If still no program found, try to extract from text blocks
    if not program:
        try:
            blocks = page_blocks(pdf_bytes)
            for block in blocks:
                text = block["text"].strip()
                # Look for IES Abroad programs
                if (re.search(r"ies\s+abroad.*milan.*business", text, re.I) or
                    re.search(r"ies\s+milan.*university.*bocconi", text, re.I) or
                    re.search(r"university.*bocconi", text, re.I)):
                    program = text
                    break
                # Look for CIEE programs
                elif re.search(r"ciee.*central.*european.*studies.*prague", text, re.I):
                    program = text
                    break
                # Look for other study abroad programs (but avoid course titles)
                elif (re.search(r"(ciee|arcadia|dis|cis|api).*", text, re.I) and 
                      len(text) > 20 and 
                      not re.search(r"course|subject|number|title", text, re.I)):
                    program = text
                    break
        except:
            pass

    # Semester
    semester = pick_by_key(["semester"], value_re=TERM_RE.pattern)
    if not semester:
        for v in fd.values():
            if TERM_RE.search(v):
                semester = v; break

    return {
        "Name": name, "StudentID": student_id, "ClassYear": class_year,
        "Date": date_val, "Program": program, "Semester": semester
    }

# ------------- Row assembly -------------
def build_rows(pdf_bytes: bytes) -> Tuple[pd.DataFrame, str, Dict[str,str]]:
    widgets, fields = read_form_widgets(pdf_bytes)
    header = infer_header_from_fields(fields, pdf_bytes)

    # Prepare column widgets by type (keep positions)
    def pick(label_substr: str):
        out = []
        for w in widgets:
            if label_substr.lower() in (w["name"] or "").lower():
                if w["value"]:
                    out.append({"page": w["page"], "y0": w["y0"], "x0": w["x0"], "value": w["value"]})
        return out

    w_elec  = pick("elecapprove")
    w_mm    = pick("majorminorapproval")
    w_comm  = pick("comments")
    w_equiv = pick("equivalent")
    w_courses_form = pick("course")  # if the template actually has Course1.. fields

    # A) Try form-based courses first
    rows = []
    indices = set()
    for w in widgets:
        m = re.search(r"(course|equivalent|elecapprove|majorminorapproval|comments)\s*([0-9]+)$", (w["name"] or ""), re.I)
        if m:
            indices.add(int(m.group(2)))
    # Collect by index if present
    for i in sorted(indices):
        c = norm_space(fields.get(f"Course{i}", "") or fields.get(f"course{i}", ""))
        eq = norm_space(fields.get(f"Equivalent{i}", "") or fields.get(f"equivalent{i}", ""))
        el = norm_space(fields.get(f"ElecApprove{i}", "") or fields.get(f"elecapprove{i}", ""))
        mm = norm_space(fields.get(f"MajorMinorApproval{i}", "") or fields.get(f"majorminorapproval{i}", ""))
        cm = norm_space(fields.get(f"Comments{i}", "") or fields.get(f"comments{i}", ""))
        if any([c, eq, el, mm, cm]):
            # Parse course code and title
            course_code, course_title = parse_course_code_and_title(c)
            # Extract program info
            program_name, city, country = extract_program_info(header.get("Program", ""))
            
            # For form-based approach, use visual signature detection
            visual_signatures = detect_visual_signatures_in_pdf(pdf_bytes, widgets)
            
            # Check if signatures exist in the approval widgets for this course
            signature_detected = {"elective": False, "major_minor": False}
            
            # Check if elective approval widget has a visual signature
            elec_widget_name = f"ElecApprove{i}"
            if elec_widget_name in visual_signatures and visual_signatures[elec_widget_name]:
                signature_detected["elective"] = True
            
            # Check if major/minor approval widget has a visual signature
            mm_widget_name = f"MajorMinorApproval{i}"
            if mm_widget_name in visual_signatures and visual_signatures[mm_widget_name]:
                signature_detected["major_minor"] = True
            
            # Map approval type using signature detection
            approval_type = map_approval_type_from_signatures(signature_detected, el, mm, cm)
            
            # Debug print
            print(f"DEBUG FORM: Course {i}")
            print(f"  ElecApprove{i}: {visual_signatures.get(elec_widget_name, False)}")
            print(f"  MajorMinorApproval{i}: {visual_signatures.get(mm_widget_name, False)}")
            print(f"  Signature detected: {signature_detected}")
            print(f"  Approval type: '{approval_type}'")
            print("---")
            
            rows.append({
                "Program/University": program_name,
                "City": city,
                "Country": country,
                "Course Code": course_code,
                "Course Title": course_title,
                "UR Equivalent": eq,
                "Major/Minor or Elective": approval_type,
                "UR Credits": "",  # Not available in current form
                "Foreign Credits": "",  # Not available in current form
                "Course Page Link": "",  # Not available in current form
                "Syllabus Link": "",  # Not available in current form
                "CourseIndex": i,
                "Original_Course": c,
                "Elective_Approval": el,
                "MajorMinor_Approval": mm,
                "Comments": cm
            })

    if rows:
        df = pd.DataFrame(rows).sort_values("CourseIndex")
        return df, "Form fields", header

    # B) No form courses → pull from text blocks (handles hyperlinks)
    courses_text = extract_courses_by_blocks(pdf_bytes)
    # For each course line, attach nearest approval/equiv/comment by y position on same page
    assembled = []
    for idx, c in enumerate(courses_text, start=1):
        near_eq  = nearest_by_y(c["y"], w_equiv, c["page"])
        near_el  = nearest_by_y(c["y"], w_elec,  c["page"])
        near_mm  = nearest_by_y(c["y"], w_mm,    c["page"])
        near_cm  = nearest_by_y(c["y"], w_comm,  c["page"])
        
        # Parse course code and title
        course_code, course_title = parse_course_code_and_title(c["Course"])
        # Extract program info
        program_name, city, country = extract_program_info(header.get("Program", ""))
        
        # Try to extract approval data from text blocks (for handwritten forms)
        text_approval_data = extract_approval_data_from_text_blocks(pdf_bytes, c["y"], c["page"])
        
        # Detect signatures in approval widgets
        signature_detected = detect_signature_in_widgets(widgets, c["y"], c["page"])
        
        # Also try visual signature detection
        visual_signatures = detect_visual_signatures_in_pdf(pdf_bytes, widgets)
        
        # Use text-based approval data if form fields are empty
        elective_approval = (near_el or {}).get("value","") or text_approval_data.get("elective", "")
        major_minor_approval = (near_mm or {}).get("value","") or text_approval_data.get("major_minor", "")
        comments = (near_cm or {}).get("value","") or text_approval_data.get("comments", "")
        
        # Map approval type using signature detection
        approval_type = map_approval_type_from_signatures(
            signature_detected,
            elective_approval,
            major_minor_approval,
            comments
        )
        
        # Debug: Store signature detection info
        signature_debug = {
            "course_y": c["y"],
            "signature_detected": signature_detected,
            "text_approval_data": text_approval_data,
            "near_el_value": (near_el or {}).get("value",""),
            "near_mm_value": (near_mm or {}).get("value",""),
            "final_approval_type": approval_type
        }
        
        # Debug print to see what's happening
        print(f"DEBUG: Course Y={c['y']:.1f}")
        print(f"  Text approval data: {text_approval_data}")
        print(f"  Signature detected: {signature_detected}")
        print(f"  Approval type: '{approval_type}'")
        
        assembled.append({
            "Program/University": program_name,
            "City": city,
            "Country": country,
            "Course Code": course_code,
            "Course Title": course_title,
            "UR Equivalent": (near_eq or {}).get("value",""),
            "Major/Minor or Elective": approval_type,
            "UR Credits": "",  # Not available in current form
            "Foreign Credits": "",  # Not available in current form
            "Course Page Link": "",  # Not available in current form
            "Syllabus Link": "",  # Not available in current form
            "CourseIndex": idx,
            "Original_Course": c["Course"],
            "Elective_Approval": elective_approval,
            "MajorMinor_Approval": major_minor_approval,
            "Comments": comments,
            "Debug_Signature_Detected": str(signature_detected),
            "Debug_Course_Y": c["y"],
        })

    if assembled:
        df = pd.DataFrame(assembled)
        # drop rows with totally empty course (paranoia)
        df = df[df["Original_Course"].str.strip().ne("")]
        return df, "Text blocks (y-aligned)", header

    # C) Last resort: OCR → parse courses from OCR text
    ocr = ocr_text(pdf_bytes, dpi=300)
    lines = []
    for l in ocr.splitlines():
        line_clean = l.strip()
        if COURSE_LINE_RE.match(line_clean):
            # Check if this line matches any exclusion patterns
            should_exclude = False
            exclude_patterns = [
                r"^THE\s+COLLEGE", r"^COURSE\s+APPROVAL", r"^IES\s+Abroad",
                r"^DEPARTMENT\s+OR\s+OFFICE", r"^STUDENTS\s+Complete",
                r"^AUTHORIZED\s+APPROVERS", r"^HOW\s+TO\s+TRANSFER",
                r"^FORM\s*$", r"^APPROVAL\s*$", r"^COLLEGE\s*$", r"^COURSE\s*$"
            ]
            for pattern in exclude_patterns:
                if re.match(pattern, line_clean, re.I):
                    should_exclude = True
                    break
            if not should_exclude:
                lines.append(l)
    
    if lines:
        assembled_ocr = []
        for i, l in enumerate(lines, start=1):
            course_text = clean_course_text(l)
            course_code, course_title = parse_course_code_and_title(course_text)
            program_name, city, country = extract_program_info(header.get("Program", ""))
            
            assembled_ocr.append({
                "Program/University": program_name,
                "City": city,
                "Country": country,
                "Course Code": course_code,
                "Course Title": course_title,
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
        
        df = pd.DataFrame(assembled_ocr)
        return df, "OCR (courses only)", header

    return pd.DataFrame(), "None", header

# ------------- Streamlit UI -------------
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

# Process files
all_results = []
all_headers = []

for i, (pdf_file, file_name) in enumerate(zip(pdf_files, file_names)):
    st.write(f"Processing {file_name}...")
    pdf_bytes = pdf_file.read()
    
    with st.spinner(f"Parsing {file_name}..."):
        df, path, header = build_rows(pdf_bytes)
    
    if not df.empty:
        # Add source file column
        df['Source File'] = file_name
        all_results.append(df)
        all_headers.append(header)
        st.success(f"✓ {file_name}: {len(df)} course(s) extracted via **{path}**")
    else:
        st.warning(f"⚠ {file_name}: No courses detected")

# Combine all results
if all_results:
    combined_df = pd.concat(all_results, ignore_index=True)
    st.subheader(f"Combined Results ({len(combined_df)} total courses from {len(all_results)} files)")
else:
    combined_df = pd.DataFrame()
    st.error("No courses detected from any files.")

# Display results
if combined_df.empty:
    st.error("No courses detected from any files. Try clearer scans or different files.")
else:
    # Create the final output DataFrame with only the desired columns
    output_columns = [
        "Source File", "Program/University", "City", "Country", "Course Code", "Course Title",
        "UR Equivalent", "Major/Minor or Elective", "UR Credits", "Foreign Credits",
        "Course Page Link", "Syllabus Link"
    ]
    
    # Ensure all columns exist in the DataFrame
    for col in output_columns:
        if col not in combined_df.columns:
            combined_df[col] = ""
    
    # Filter to only include the desired columns
    final_df = combined_df[output_columns].copy()
    
    # Display the data without filter row
    st.dataframe(final_df, use_container_width=True)
    
    # For download, create CSV without filter row
    csv_data = final_df.to_csv(index=False)
    st.download_button("Download Combined Results as CSV", csv_data.encode("utf-8"),
                       file_name="caf_bulk_results.csv", mime="text/csv")
    
    # Show debug info in expander
    with st.expander("Debug: Original Data"):
        st.dataframe(combined_df, use_container_width=True)
    
    # Show signature detection debug info
    with st.expander("Debug: Signature Detection"):
        st.write("This shows which approval widgets have signatures detected:")
        widgets, fields = read_form_widgets(pdf_bytes)
        
        # Show ALL widgets first to see what we're working with
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
        
        # Now show signature detection
        st.write("**Signature Detection Results:**")
        signature_widgets = []
        for w in widgets:
            widget_name = (w["name"] or "").lower()
            widget_value = (w["value"] or "").strip()
            
            # Check if it's an approval-related widget
            is_approval_widget = "elec" in widget_name or any(term in widget_name for term in ["major", "minor"])
            
            if is_approval_widget:
                has_signature = widget_value and widget_value.lower() not in ["", "no", "n", "none", "yes", "y", "approved", "denied"]
                signature_widgets.append({
                    "Widget Name": w["name"],
                    "Value": widget_value,
                    "Page": w["page"],
                    "Y Position": round(w["y0"], 1),
                    "Type": "Elective" if "elec" in widget_name else "Major/Minor",
                    "Has Signature": has_signature
                })
        
        if signature_widgets:
            st.dataframe(pd.DataFrame(signature_widgets), use_container_width=True)
        else:
            st.write("No approval widgets found.")
        
        # Show visual signature detection results
        st.write("**Visual Signature Detection Results:**")
        visual_signatures = detect_visual_signatures_in_pdf(pdf_bytes, widgets)
        visual_results = []
        for widget_name, has_signature in visual_signatures.items():
            if "elec" in widget_name.lower() or "major" in widget_name.lower() or "minor" in widget_name.lower():
                visual_results.append({
                    "Widget Name": widget_name,
                    "Has Visual Signature": has_signature
                })
        
        if visual_results:
            st.dataframe(pd.DataFrame(visual_results), use_container_width=True)
        else:
            st.write("No visual signatures detected.")

with st.expander("Debug: Header & Raw Form Fields"):
    st.write("Header inference:", header)
    widgets, fields = read_form_widgets(pdf_bytes)
    st.write("Raw field keys (sample):", list(fields.keys())[:50])