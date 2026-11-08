"""Build the desktop app for the computer this runs on.

    pip install -r requirements.txt -r desktop/requirements.txt
    python desktop/build.py

macOS:   dist/Innerbloom.app, then dist/Innerbloom-mac-<arch>.dmg
Windows: dist/Innerbloom/Innerbloom.exe, then dist/Innerbloom-windows.zip

GitHub builds both on every version tag (.github/workflows/desktop.yml).
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SEP = ";" if platform.system() == "Windows" else ":"


def icon() -> str:
    """PyInstaller turns the PNG into .icns or .ico itself (needs Pillow)."""
    return str(ROOT / "desktop" / "icon.png")


def pyinstaller() -> None:
    data = [("index.html", "."), ("assets", "assets"), ("desktop/setup.html", "desktop")]
    args = [sys.executable, "-m", "PyInstaller", str(ROOT / "desktop" / "launcher.py"),
            "--name", "Innerbloom", "--windowed", "--noconfirm", "--clean",
            "--icon", icon(), "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
            "--specpath", str(ROOT / "build"),
            "--paths", str(ROOT),
            "--hidden-import", "app", "--hidden-import", "desktop.setup_routes",
            "--collect-submodules", "uvicorn", "--collect-submodules", "innerbloom_core",
            "--osx-bundle-identifier", "com.innerbloom.journal"]
    for src, dest in data:
        args += ["--add-data", f"{ROOT / src}{SEP}{dest}"]
    subprocess.run(args, check=True, cwd=ROOT)


def package() -> Path:
    system = platform.system()
    if system == "Darwin":
        arch = "apple-silicon" if platform.machine() == "arm64" else "intel"
        out = DIST / f"Innerbloom-mac-{arch}.dmg"
        stage = DIST / "dmg"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir()
        subprocess.run(["ditto", str(DIST / "Innerbloom.app"), str(stage / "Innerbloom.app")], check=True)
        (stage / "Applications").symlink_to("/Applications")
        out.unlink(missing_ok=True)
        subprocess.run(["hdiutil", "create", "-volname", "Innerbloom", "-srcfolder", str(stage),
                        "-ov", "-format", "UDZO", str(out)], check=True)
        shutil.rmtree(stage)
        return out
    if system == "Windows":
        out = DIST / "Innerbloom-windows"
        return Path(shutil.make_archive(str(out), "zip", DIST, "Innerbloom"))
    out = DIST / "Innerbloom-linux"
    return Path(shutil.make_archive(str(out), "gztar", DIST, "Innerbloom"))


def main() -> int:
    pyinstaller()
    out = package()
    print(f"built {out} ({out.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
