@echo off
echo Starting CAF Extractor...
echo The application will open in your web browser.
echo Close this window to stop the application.
echo ----------------------------------------

cd /d "%~dp0"
python -m streamlit run caf.py --server.headless false --server.port 8501

pause

