@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
python -m pytest
