@echo off
setlocal

echo ============================================
echo   CCFII Display Share - Windows Build
echo ============================================
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"
if %errorlevel% neq 0 (
    echo.
    echo [!] Build failed.
    pause
    exit /b %errorlevel%
)

echo.
echo [OK] Build completed successfully.
pause
