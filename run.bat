@echo off
echo Starting Display Share...
echo.
python server.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Server exited with an error.
)
pause
