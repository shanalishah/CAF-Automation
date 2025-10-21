# Repository Overview: CAF-Automation

## 📖 What Is This Repository?

**CAF-Automation** (Course Approval Form Automation) is a Python-based web application that automatically extracts and processes data from Course Approval Form (CAF) PDF documents. It's designed for educational institutions to streamline the processing of study abroad course approval forms.

## 🎯 Purpose & Use Case

This tool solves the problem of manually extracting information from Course Approval Forms - PDF documents that students submit when seeking approval for courses taken at foreign universities. Instead of manually reading and transcribing information from these PDFs, the tool:

1. **Automatically extracts** course information from PDF forms
2. **Detects approval status** (elective, major/minor, or not approved)
3. **Exports data to CSV** for easy processing and record-keeping

### Target Users
- Academic advisors
- Study abroad offices
- Registrar's offices
- Administrative staff processing course approvals

## 🏗️ Technical Architecture

### Core Technology Stack

```
┌─────────────────────────────────────┐
│     Streamlit Web Interface          │
│  (User uploads PDF, views results)   │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      PDF Processing Engine           │
│  • PyMuPDF (Form Field Extraction)   │
│  • pdf2image (Image Conversion)      │
│  • Pytesseract (OCR for handwriting) │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       Data Extraction Logic          │
│  • Pattern matching (course codes)   │
│  • Signature detection               │
│  • Approval status determination     │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│         Output Generation            │
│  • Structured table display          │
│  • CSV export (Pandas DataFrame)     │
└──────────────────────────────────────┘
```

### Key Dependencies
- **Streamlit**: Web interface framework
- **PyMuPDF (fitz)**: PDF form field extraction and text parsing
- **pdf2image**: Convert PDF pages to images for OCR
- **Pytesseract**: OCR engine for extracting handwritten text
- **Pillow (PIL)**: Image processing
- **Pandas**: Data manipulation and CSV export
- **NumPy**: Numerical operations

## 📁 Repository Structure

```
CAF-Automation/
│
├── caf.py                          # Main application (1,324 lines)
│   └── Core Streamlit web app with PDF processing logic
│
├── run_caf.py                      # Python launcher script
│   └── Cross-platform launcher for easy startup
│
├── run_caf.sh                      # Bash launcher (Linux/macOS)
├── run_caf.bat                     # Windows batch launcher
├── Start_CAF_Extractor.command     # macOS application launcher
├── CAF_Extractor.scpt              # AppleScript launcher
├── CAF_Extractor.app/              # macOS application bundle
│
├── requirements.txt                # Python package dependencies
├── packages.txt                    # System packages for deployment
├── testcaf.pdf                     # Sample test PDF (1.3 MB)
│
├── README.md                       # User documentation
└── .gitignore                      # Git ignore rules
```

## 🔍 How It Works

### 1. **PDF Upload**
Users upload a CAF PDF through the Streamlit web interface.

### 2. **Multi-Stage Extraction**
The application uses a three-tier extraction approach:

#### Tier 1: Form Field Extraction
- Extracts data from PDF form fields (structured data)
- Fastest and most accurate when forms are properly filled

#### Tier 2: Text Layer Extraction
- Falls back to extracting text directly from the PDF
- Handles PDFs where form fields aren't used

#### Tier 3: OCR (Optical Character Recognition)
- Converts PDF pages to images
- Uses Tesseract OCR to extract handwritten text
- Critical for detecting handwritten signatures and notes

### 3. **Data Processing**

#### Course Code Recognition
The tool recognizes multiple course code formats:
- `(GI) Econ 3006 PRCZ Economics of the European Union`
- `CU 270-01 - 2163268-Culture and Cuisine`
- `BOCCONI 30150 - Introduction to Options and Futures`
- `FI 356 - International Financial Markets and Investments`
- `POLI 3003 PRAG The Rise and Fall...`
- `BBLCO1221U – Corporate Finance`

#### Approval Detection
Determines approval type by detecting:
- **Handwritten signatures** (e.g., "Rohan Palma")
- **Typed signatures/initials** in form fields
- **Comments** like "INTR: PPD", "INTR: GoN; PaC"
- **Rejection indicators** like "Not approved"

### 4. **Data Output**

Extracted data includes:
- Program/University name
- City & Country
- Course Code
- Course Title
- UR (University of Rochester) Equivalent
- Major/Minor or Elective classification
- UR Credits
- Foreign Credits
- Course Page Link
- Syllabus Link

### 5. **Export**
Results are displayed in a table and can be downloaded as CSV.

## 🚀 Deployment Options

### 1. **Streamlit Cloud** (Current Deployment)
- **Live URL**: https://caf-automation.streamlit.app/
- Fully hosted, no installation required
- Includes Tesseract OCR support
- Free tier available

### 2. **Local Installation**
```bash
# Install dependencies
pip install streamlit PyMuPDF pdf2image pytesseract pillow pandas

# Install Tesseract OCR
brew install tesseract  # macOS
apt-get install tesseract-ocr  # Linux
# Download from GitHub for Windows

# Run the application
streamlit run caf.py
```

### 3. **Cross-Platform Launchers**
- **macOS**: Double-click `Start_CAF_Extractor.command`
- **Windows**: Double-click `run_caf.bat`
- **Linux**: Run `./run_caf.sh`
- **Any OS**: `python3 run_caf.py`

## 🎨 Key Features

### ✅ Implemented Features
1. **PDF Upload Interface** - Drag-and-drop file upload
2. **Multi-Format Support** - Handles various course code formats
3. **Signature Detection** - Both handwritten and typed
4. **Approval Classification** - Elective vs. Major/Minor vs. Not Approved
5. **CSV Export** - Download processed data
6. **Cross-Platform** - Works on Windows, macOS, Linux
7. **Cloud Deployment** - Accessible via web browser
8. **Debug Mode** - Shows extraction details for troubleshooting
9. **Row Alignment** - Uses y-position to align multi-page courses

### 🔧 Technical Highlights

#### Intelligent Text Extraction
The application uses a sophisticated y-position-based row mapping system to:
- Align courses that span multiple lines
- Group related form fields together
- Handle multi-page forms correctly

#### Robust Pattern Matching
- Uses regular expressions to extract course codes from varied formats
- Handles edge cases like:
  - Courses with prefixes: `(GI) Econ 3006`
  - Courses with internal IDs: `CU 270-01 - 2163268`
  - Courses with em-dashes: `BBLCO1221U – Corporate Finance`

#### Signature Detection Logic
- Analyzes form field values for signatures
- Detects handwritten signatures via OCR
- Recognizes signature patterns in comments
- Filters out non-signature text (e.g., "yes", "approved", "n/a")

## 📊 Code Statistics

- **Main Application**: 1,324 lines (caf.py)
- **Launcher Script**: 47 lines (run_caf.py)
- **Total Python Code**: 1,371 lines
- **Dependencies**: 7 Python packages
- **System Packages**: 2 (Tesseract OCR)

## 🔒 Security Considerations

- No sensitive data is stored persistently
- PDFs are processed in memory
- Uploaded files are temporary (Streamlit session-based)
- Note in README: "Ensure you have proper permissions to process the PDF files"

## 🌍 Supported Programs

The tool is designed to work with CAFs from various study abroad programs:
- IES Abroad (Milan, Barcelona, etc.)
- CIEE (Prague, etc.)
- University of Bocconi
- Various international universities

## 🐛 Known Limitations & Troubleshooting

### Common Issues Addressed
1. **Missing Dependencies** - Clear installation instructions
2. **Tesseract Not Found** - PATH configuration guidance
3. **PDF Processing Errors** - Suggestions for password-protected PDFs
4. **OCR Accuracy** - Dependent on PDF quality and handwriting clarity

### Debug Features
- Expandable debug section in UI
- Shows raw extracted text
- Displays detected form fields
- Helps diagnose extraction issues

## 📝 License & Authorship

- **License**: MIT License
- **Author**: Shanali Shah ([@shanalishah](https://github.com/shanalishah))
- **Purpose**: Educational and administrative use

## 🎓 Educational Context

This tool appears to be built for the University of Rochester (UR) Study Abroad Office, as evidenced by:
- References to "UR Credits" and "UR Equivalent"
- Support for study abroad programs commonly used by US universities
- Focus on academic approval workflows

## 🔄 Maintenance Status

Based on the git history:
- Recently updated with improved OCR and debugging features
- Active development for handling edge cases
- Focus on robustness and signature detection

## 💡 Use Case Example

**Before (Manual Process)**:
1. Staff receives CAF PDF via email
2. Opens PDF and manually reads each field
3. Copies information into spreadsheet
4. Checks for signatures/approvals
5. Repeats for hundreds of forms

**After (Automated Process)**:
1. Upload PDF to web interface
2. Tool extracts all information in seconds
3. Review results in table format
4. Download CSV with all data
5. Process hundreds of forms quickly

## 🚀 Getting Started (Quick Start)

1. **Online**: Visit https://caf-automation.streamlit.app/
2. **Local**: Run `python3 run_caf.py` or `streamlit run caf.py`
3. **Upload** a CAF PDF
4. **Review** extracted data
5. **Download** CSV if needed

---

## Summary

**CAF-Automation is a specialized web application that automates the extraction and processing of Course Approval Forms from PDFs, saving administrative staff significant time and reducing manual data entry errors. It uses advanced PDF parsing, OCR technology, and intelligent pattern matching to extract course information, detect approval signatures, and export structured data.**
