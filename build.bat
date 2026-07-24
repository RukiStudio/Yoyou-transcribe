@echo off
chcp 65001 >nul
setlocal

echo [1/2] Installing project dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/2] Building Ruki Music Transcriber...
python build.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\RukiMusicTranscriber\RukiMusicTranscriber.exe
pause
exit /b 0

:error
echo.
echo Build failed. Review the messages above and ensure Python 3.10-3.13 is installed.
pause
exit /b 1
