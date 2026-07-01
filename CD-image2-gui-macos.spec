# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['CD_image2_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('chedankj-cd-egg-solid-logo.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CD-image2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CD-image2',
)

app = BUNDLE(
    coll,
    name='CD-image2.app',
    icon='chedankj-cd-egg-solid-logo.icns',
    bundle_identifier='com.cd.image2',
    info_plist={
        'CFBundleName': 'CD-image2',
        'CFBundleDisplayName': 'CD-image2',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)
