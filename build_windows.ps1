$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "dist\chedan-image2-gui.exe" -Force -ErrorAction SilentlyContinue

python -m PyInstaller --clean .\chedan-image2-gui.spec

if (-not (Test-Path -LiteralPath "dist\chedan-image2-gui.exe")) {
    throw "Build failed: dist\chedan-image2-gui.exe was not created."
}

Write-Host "Built Windows app: dist\chedan-image2-gui.exe"
