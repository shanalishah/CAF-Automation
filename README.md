# CAF Extractor - Course Approval Form Automation

A Python-based tool for automatically extracting and processing data from Course Approval Forms (CAF) PDFs. This tool uses Streamlit for the web interface and PyMuPDF for PDF processing.

## 🚀 Features

- **PDF Upload & Processing**: Upload CAF PDFs and extract course information automatically
- **Multi-format Support**: Handles various course code formats and handwritten signatures
- **Approval Detection**: Automatically detects elective, major/minor, and approval status
- **Data Export**: Export extracted data to CSV format
- **Cross-platform**: Works on Windows, macOS, and Linux

## 📋 Extracted Data Fields

- Program/University
- City & Country
- Course Code & Title
- UR Equivalent
- Major/Minor or Elective classification
- UR Credits & Foreign Credits
- Course Page Link & Syllabus Link

## 🛠️ Installation

### Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/shanalishah/CAFautomation.git
   cd CAFautomation
   ```

2. **Install required packages:**
   ```bash
   pip install streamlit PyMuPDF pdf2image pytesseract pillow pandas
   ```

3. **Install Tesseract OCR (for text extraction):**
   
   **macOS:**
   ```bash
   brew install tesseract
   ```
   
   **Windows:**
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Add to PATH
   
   **Linux (Ubuntu/Debian):**
   ```bash
   sudo apt-get install tesseract-ocr
   ```

## 🌐 Live Demo

**Try the application online:** [CAF Extractor on Streamlit Cloud](https://caf-automation.streamlit.app/)

## 🚀 Usage

### Method 1: Streamlit Web Interface (Recommended)

1. **Start the application:**
   ```bash
   python3 -m streamlit run caf.py --server.headless false --server.port 8501
   ```

2. **Open your browser** and go to: `http://localhost:8501`

3. **Upload a CAF PDF** using the file uploader

4. **View and download** the extracted results

### Method 2: Command Line Scripts

**macOS/Linux:**
```bash
./run_caf.sh
```

**Windows:**
```cmd
run_caf.bat
```

**Python:**
```bash
python3 run_caf.py
```

### Method 3: macOS Application

Double-click `Start_CAF_Extractor.command` to launch the application.

## 📁 Project Structure

```
CAFautomation/
├── caf.py                          # Main Streamlit application
├── run_caf.py                      # Python launcher script
├── run_caf.sh                      # Bash launcher script
├── run_caf.bat                     # Windows batch launcher
├── Start_CAF_Extractor.command     # macOS application launcher
├── CAF_Extractor.scpt              # AppleScript launcher
├── testcaf.pdf                     # Sample PDF for testing
├── README.md                       # This file
└── .gitignore                      # Git ignore rules
```

## 🔧 Supported Course Formats

The tool recognizes various course code formats:

- `(GI) Econ 3006 PRCZ Economics of the European Union`
- `CU 270-01 - 2163268-Culture and Cuisine`
- `BOCCONI 30150 - Introduction to Options and Futures`
- `FI 356 - International Financial Markets and Investments`
- `POLI 3003 PRAG The Rise and Fall of Central European Totalitarianism`
- `CU 270: Culture and Cuisine`
- `BBLCO1221U – Corporate Finance`

## 🎯 Approval Detection

The tool automatically detects:

- **Elective Approval**: Handwritten signatures like "Rohan Palma"
- **Major/Minor Approval**: Comments like "INTR: PPD", "INTR: GoN; PaC"
- **Not Approved**: Comments containing "Not approved"
- **General Credit**: Text like "general credit"

## 🌍 Supported Programs

- IES Abroad programs (Milan, Barcelona, etc.)
- CIEE programs (Prague, etc.)
- University of Bocconi
- Various study abroad institutions

## 🐛 Troubleshooting

### Common Issues

1. **"No module named streamlit"**
   ```bash
   pip install streamlit
   ```

2. **Tesseract not found**
   - Install Tesseract OCR following the installation instructions above
   - Ensure it's added to your system PATH

3. **PDF processing errors**
   - Ensure the PDF is not password-protected
   - Try with a different PDF file
   - Check that the PDF contains form fields or readable text

### Debug Mode

The application includes debug information in an expandable section to help troubleshoot extraction issues.

## ☁️ Deployment

### Streamlit Cloud Deployment

This application is deployed on Streamlit Cloud for easy access:

1. **Visit the live app**: [CAF Extractor on Streamlit Cloud](https://caf-automation.streamlit.app/)
2. **Upload your CAF PDF** directly in the browser
3. **Download results** as CSV

### Deploy Your Own Version

To deploy your own version on Streamlit Cloud:

1. **Fork this repository** on GitHub
2. **Go to [share.streamlit.io](https://share.streamlit.io)**
3. **Connect your GitHub account**
4. **Select your forked repository**
5. **Set the main file path** to `caf.py`
6. **Click "Deploy!"**

The deployment includes:
- ✅ Automatic dependency installation
- ✅ Tesseract OCR support
- ✅ File upload and processing
- ✅ CSV download functionality

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👥 Authors

- **Shanali Shah** - *Initial work* - [shanalishah](https://github.com/shanalishah)

## 🙏 Acknowledgments

- PyMuPDF for PDF processing
- Streamlit for the web interface
- Tesseract OCR for text extraction
- The academic community for feedback and testing

## 📞 Support

If you encounter any issues or have questions:

1. Check the troubleshooting section above
2. Search existing issues on GitHub
3. Create a new issue with detailed information about your problem

---

**Note**: This tool is designed for educational and administrative purposes. Ensure you have proper permissions to process the PDF files you're working with.
