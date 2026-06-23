@echo off
setlocal
cd /d "%~dp0"
echo === heimdall-timewatch GUI (PyInstaller) ===

python -m pip install -r requirements-gui.txt
if errorlevel 1 exit /b 1

pyinstaller heimdall-gui.spec --noconfirm --clean
if errorlevel 1 exit /b 1

echo.
echo OK: dist\heimdall-timewatch-gui\heimdall-timewatch-gui.exe
echo Config: %%APPDATA%%\HeimdallTimeWatch\
endlocal
