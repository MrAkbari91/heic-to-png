# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

a = Analysis(
    ['convert_heic_to_png.py'],
    pathex=[],
    binaries=collect_dynamic_libs('pillow_heif'),
    datas=[
        ('heic_to_any.ico', '.'),
        *collect_data_files('customtkinter'),
    ],
    hiddenimports=['gui', '_pillow_heif', 'customtkinter', 'darkdetect'],
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
    a.binaries,
    a.datas,
    [],
    name='HEIC-Converter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='heic_to_any.ico',
)
