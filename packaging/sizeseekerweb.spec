# PyInstaller spec - build with:  pyinstaller packaging/sizeseekerweb.spec --noconfirm
# Produces dist/SizeSeekerWeb/ (one folder, no console window).
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "sizeseekerweb" / "static"), "sizeseekerweb/static")],
    hiddenimports=["pystray._win32"],
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SizeSeekerWeb",
    icon=str(ROOT / "packaging" / "icon.ico"),
    console=False,
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(exe, a.binaries, a.datas, name="SizeSeekerWeb")
