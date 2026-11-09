@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python -m venv .venv
) else (
  py -m venv .venv
)
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pytest
