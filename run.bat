@echo off
echo Starting CCFII Display Share...
echo.
pythonw run.pyw %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Desktop app could not start. Falling back to CLI mode...
    python launcher.py --cli %*
)
pause
