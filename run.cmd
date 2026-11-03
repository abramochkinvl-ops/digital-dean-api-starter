@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
 echo Run setup.cmd first.
 exit /b 1
)
call .venv\Scripts\activate.bat
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
