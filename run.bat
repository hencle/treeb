@echo off
python -m venv .venv
call .venv\Scripts\activate
pip install flask
python app.py
pause
