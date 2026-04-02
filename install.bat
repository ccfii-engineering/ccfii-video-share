@echo off
echo ============================================
echo   CCFII Display Share — Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Python not found. Installing via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo [!] Please restart this script after Python installs.
    pause
    exit /b 1
) else (
    echo [OK] Python found.
)

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] FFmpeg not found. Installing via winget...
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    echo [!] Please restart this script after FFmpeg installs.
    pause
    exit /b 1
) else (
    echo [OK] FFmpeg found.
)

:: Install Python dependencies
echo [*] Installing Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] pip install failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Installation complete!
echo   Run "run.bat" to start sharing.
echo ============================================
pause
