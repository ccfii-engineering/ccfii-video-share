$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$logoPng = Join-Path $root "assets\ccfii-logo.png"
$logoIco = Join-Path $root "assets\ccfii-logo.ico"

function Install-InnoSetup {
    Write-Host "Inno Setup not found. Attempting to install it..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id JRSoftware.InnoSetup --exact --accept-package-agreements --accept-source-agreements
        return
    }

    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install innosetup --no-progress -y
        return
    }

    throw "Inno Setup 6 is required. Install it manually or add winget/choco to PATH."
}

Write-Host "Installing packaging dependencies..."
python -m pip install pyinstaller pillow
python -m pip install -r requirements.txt

Write-Host "Generating ICO from PNG logo..."
python -c "from PIL import Image; img = Image.open(r'$logoPng').convert('RGBA'); img.save(r'$logoIco', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

Write-Host "Building desktop executable..."
python -m PyInstaller CCFIIDisplayShare.spec --noconfirm

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not (Test-Path $iscc)) {
    Install-InnoSetup
    $iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not (Test-Path $iscc)) {
    throw "Inno Setup 6 could not be found after installation."
}

Write-Host "Building Windows installer..."
& $iscc "installer\CCFIIDisplayShare.iss"

Write-Host "Installer build complete."
