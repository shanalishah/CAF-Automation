#!/usr/bin/env python3
"""
CAF Automation Launcher
Double-click this file to run the CAF Extractor application.
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    """Launch the CAF Extractor Streamlit app."""
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.absolute()
    caf_script = script_dir / "caf.py"
    
    # Check if caf.py exists
    if not caf_script.exists():
        print("Error: caf.py not found in the same directory as this script.")
        print(f"Looking for: {caf_script}")
        input("Press Enter to exit...")
        return
    
    print("Starting CAF Extractor...")
    print("The application will open in your web browser.")
    print("Close this window to stop the application.")
    print("-" * 50)
    
    try:
        # Run streamlit with the caf.py file
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            str(caf_script),
            "--server.headless", "false",
            "--server.port", "8501"
        ], cwd=script_dir)
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
    except Exception as e:
        print(f"Error running application: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()

