@echo off
rem Create a user step by step. Run from a terminal (.\create_user.bat) or double-click it.
cd /d "%~dp0"
set PYTHONWARNINGS=ignore
".venv\Scripts\python.exe" -m scripts.create_user %*
echo.
pause
