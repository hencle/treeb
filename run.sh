#!/usr/bin/env bash
# ─── self-make-executable & re-exec ───
if [[ "${BASH_SOURCE[0]}" == "$0" && ! -x "$0" ]]; then
  chmod +x "$0"
  exec "$0" "$@"
fi

set -e

# Check if python3 is available, otherwise try python
PYTHON_CMD=python3
if ! command -v python3 &> /dev/null
then
    PYTHON_CMD=python
    if ! command -v python &> /dev/null
    then
        echo "Error: Python (as python3 or python) is not installed or not in PATH."
        exit 1
    fi
fi

echo "Using $($PYTHON_CMD --version)"

# --- Check for tkinter ---
echo "Checking for tkinter availability..."
# Try to import tkinter. If it fails, print a message.
# The `python -c "..."` command will exit with non-zero status on import error.
if $PYTHON_CMD -c "import tkinter; tkinter.Tk().destroy()" &> /dev/null; then
    echo "tkinter is available."
else
    echo "----------------------------------------------------------------------------------"
    echo "WARNING: Python module 'tkinter' not found or failed to initialize!"
    echo "The 'Browse for directory' feature in the UI will be disabled."
    echo "This might be due to a missing tkinter package or no available display server (X11/WSLg)."
    echo ""
    echo "To enable this feature, please ensure tkinter is installed and a display is accessible:"
    echo "  Common Linux commands to install tkinter for Python 3:"
    echo "    Debian/Ubuntu: sudo apt-get update && sudo apt-get install python3-tk"
    echo "    Fedora:        sudo dnf install python3-tkinter"
    echo "    CentOS/RHEL:   sudo yum install python3-tkinter"
    echo "    Arch Linux:    sudo pacman -S tk"
    echo ""
    echo "  macOS (if using Homebrew Python): Usually included. If not: brew install python-tk"
    echo "  Windows: Usually included with Python from python.org. Ensure 'tcl/tk and IDLE'"
    echo "           was selected during installation, or reinstall Python with this option."
    echo ""
    echo "If tkinter is installed but fails to initialize (e.g., 'no display name' error),"
    echo "ensure you are running in a graphical environment or have X11 forwarding set up correctly."
    echo "----------------------------------------------------------------------------------"
    # The app will still attempt to run, with the feature gracefully disabled.
fi
# --- End tkinter check ---


# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment .venv..."
    $PYTHON_CMD -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
# shellcheck disable=SC1091
. .venv/bin/activate

# Install/upgrade pip and install requirements
echo "Installing/checking dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Starting Flask app (http://127.0.0.1:5000)..."
python app.py