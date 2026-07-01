$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "dist\CD-image2.exe" -Force -ErrorAction SilentlyContinue

python -m PyInstaller --clean .\CD-image2-gui.spec

if (-not (Test-Path -LiteralPath "dist\CD-image2.exe")) {
    throw "Build failed: dist\CD-image2.exe was not created."
}

Write-Host "Built Windows app: dist\CD-image2.exe"
