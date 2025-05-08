#!/usr/bin/env bash
# ─── self-make-executable & re-exec ───
if [[ "${BASH_SOURCE[0]}" == "$0" && ! -x "$0" ]]; then
  chmod +x "$0"
  exec "$0" "$@"
fi

set -e

python3 -m venv .venv
. .venv/bin/activate
pip install flask
python app.py
