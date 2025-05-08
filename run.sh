#!/usr/bin/env bash
set -e
python3 -m venv .venv
. .venv/bin/activate
pip install flask
python app.py
