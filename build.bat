@echo off
REM Build lengkap di Windows (Python 3.11-3.13 disarankan). Hasil: dist\VibeMotionNext\VibeMotionNext.exe
python -m pip install -r requirements-dev.txt || exit /b 1
python tools\build.py --zip --installer || exit /b 1
echo.
echo Selesai. Lihat folder dist\
