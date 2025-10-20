#!/bin/bash

echo "Starting CAF Extractor..."
echo "The application will open in your web browser."
echo "Close this window to stop the application."
echo "----------------------------------------"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if caf.py exists
if [ ! -f "caf.py" ]; then
    echo "Error: caf.py not found in the same directory as this script."
    echo "Looking for: $SCRIPT_DIR/caf.py"
    read -p "Press Enter to exit..."
    exit 1
fi

# Run streamlit
python3 -m streamlit run caf.py --server.headless false --server.port 8501

echo "Application stopped."
read -p "Press Enter to exit..."





