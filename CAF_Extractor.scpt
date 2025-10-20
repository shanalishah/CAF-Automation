tell application "Terminal"
    activate
    do script "cd '" & (POSIX path of (path to me as string)) & "' && python3 -m streamlit run caf.py --server.headless false --server.port 8501"
end tell





