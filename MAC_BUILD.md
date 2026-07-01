# macOS Build

This project can be packaged as a double-clickable macOS app on a Mac.

Important: macOS apps must be built on macOS. PyInstaller cannot cross-build a working `.app` from Windows.

## Build

Copy this project folder to a Mac, open Terminal in the project folder, then run:

```bash
chmod +x build_macos.sh
./build_macos.sh
```

Outputs:

- `dist/CD-image2.app`
- `dist/CD-image2-macOS-app.zip`
- `dist/CD-image2-macOS.dmg` if `hdiutil` is available
- `dist/CD-image2-macOS.pkg` if `pkgbuild` is available

The build script also converts `chedankj-cd-egg-solid-logo.png` into a macOS `.icns` app icon automatically.

## Build Without Owning a Mac

This repo includes a GitHub Actions workflow at `.github/workflows/build-macos.yml`.

Push the project to GitHub, then run `Build macOS App` from the Actions tab. The workflow uses GitHub's macOS runner and uploads:

- `CD-image2.app`
- `CD-image2-macOS-app.zip`
- `CD-image2-macOS.dmg`
- `CD-image2-macOS.pkg`

## Use

Double-click `CD-image2.app`, distribute `dist/CD-image2-macOS.dmg`, or install with `dist/CD-image2-macOS.pkg`.

On first launch, macOS Gatekeeper may warn if the app is not signed and notarized:

1. Right-click the app.
2. Choose `Open`.
3. Confirm `Open`.

Runtime files:

- Config: `~/Library/Application Support/CD-image2/config.ini`
- Default generated images: `~/Pictures/CD-image2`

## Notes

- Build once on Apple Silicon for Apple Silicon Macs.
- Build once on Intel macOS for Intel Macs.
- For broad distribution, sign and notarize the app with an Apple Developer account.
- The API key is still entered by the user at runtime; do not bake API keys into the app package.
