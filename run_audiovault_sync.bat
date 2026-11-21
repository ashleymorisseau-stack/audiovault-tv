@echo off
REM Run Audio Vault TV Sync (the push and pull tool).
REM Double-click this file. It opens a window with two buttons:
REM Push my changes to GitHub, and Pull the latest from GitHub.
REM Put this file inside the audiovault-tv folder on the PC.
cd /d "%~dp0%"
python -c "import wx" >nul 2>&1
if errorlevel 1 (
  echo wxPython is not installed yet, Honey.
  echo Please run this once, then double-click this file again:
  echo pip install wxPython
  pause
  exit /b 1
)
python audiovault_sync.py
if errorlevel 1 (
  echo Audio Vault TV Sync closed with an error, Honey.
  echo Please tell Muse what it said above.
  pause
)
