# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).parent
ICON = ROOT / "assets" / "tutoriales-visuales.ico"
VERSION_INFO = ROOT / "packaging" / "windows-version-info.txt"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ICON), "assets"), (str(ROOT / "packaging" / "update-helper.ps1"), "packaging")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "nuitka", "tkinter"],
    noarchive=False,
    optimize=2,
)
# Qt en Windows 10+ usa ICU del sistema. PATH puede contener ICU de Poppler
# con exportaciones incompatibles; nunca distribuir esa sustitución de icuuc.
a.binaries = [entry for entry in a.binaries if entry[0].lower() != "icuuc.dll"]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TutorialesVisuales",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(VERSION_INFO),
    uac_admin=False,
    uac_uiaccess=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TutorialesVisuales",
)
