@echo off
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" /d "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0src\gui.py"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    start "" /d "%~dp0" "%~dp0.venv\Scripts\python.exe" "%~dp0src\gui.py"
) else (
    start "" /d "%~dp0" pythonw "%~dp0src\gui.py"
)