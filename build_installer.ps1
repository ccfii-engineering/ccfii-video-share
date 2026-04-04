$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logoPng = Join-Path $root "assets\ccfii-logo.png"
$logoIco = Join-Path $root "assets\ccfii-logo.ico"

Write-Host "Installing packaging dependencies..."
python -m pip install pyinstaller
python -m pip install -r requirements.txt

if (-not (Test-Path $logoIco)) {
    Write-Host "Generating ICO from PNG logo..."
    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::FromFile($logoPng)
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = New-Object System.IO.FileStream($logoIco, [System.IO.FileMode]::Create)
    $icon.Save($stream)
    $stream.Close()
    $icon.Dispose()
    $bitmap.Dispose()
}

Write-Host "Building desktop executable..."
python -m PyInstaller CCFIIDisplayShare.spec --noconfirm

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) {
    throw "Inno Setup 6 was not found at $iscc"
}

Write-Host "Building Windows installer..."
& $iscc "installer\CCFIIDisplayShare.iss"

Write-Host "Installer build complete."
