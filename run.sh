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

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment .venv..."
    $PYTHON_CMD -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
. .venv/bin/activate

# Install/upgrade pip and install requirements
echo "Installing dependencies..."
pip install --upgrade pip
pip install flask tiktoken # Added tiktoken here

echo "Starting Flask app..."
python app.py