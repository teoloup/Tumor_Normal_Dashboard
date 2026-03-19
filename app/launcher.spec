# PyInstaller spec for the Tumor Normal Variant Dashboard launcher.

from pathlib import Path
import sys

block_cipher = None
project_dir = Path.cwd()
launcher_path = project_dir / "app" / "launcher.py"
tcl_root = Path(sys.base_prefix) / "tcl"


def collect_tree(source_root: Path, target_root: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if not source_root.exists():
        return entries

    for path in source_root.rglob("*"):
        if path.is_file():
            relative_parent = path.relative_to(source_root).parent
            destination = target_root if str(relative_parent) == "." else f"{target_root}/{relative_parent.as_posix()}"
            entries.append((str(path), destination))
    return entries


datas = collect_tree(tcl_root / "tcl8.6", "_tcl_data")
datas.extend(collect_tree(tcl_root / "tk8.6", "_tk_data"))


a = Analysis(
    [str(launcher_path)],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=False,
    name="Tumor_Normal_Variant_Dashboard_Launcher",
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
    icon=None,
    runtime_tmpdir=".",
)
