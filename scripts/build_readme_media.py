"""Render the README animations in docs/media from the scenes in docs/media/src.

Each scene is a small HTML page with a render(t) function and a DURATION, so
every frame is exact rather than a screen recording. Needs Playwright with
Chromium and ffmpeg (set FFMPEG if it is not on PATH).

    python scripts/build_readme_media.py            # all scenes
    python scripts/build_readme_media.py banner     # one scene
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "media" / "src"
OUT = ROOT / "docs" / "media"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FPS = 12


def build(page, name):
    page.goto((SRC / f"{name}.html").as_uri())
    page.wait_for_timeout(400)  # fonts
    size = page.evaluate("[document.body.offsetWidth, document.body.offsetHeight]")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    duration = page.evaluate("DURATION")
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(int(duration * FPS)):
            page.evaluate(f"render({i / FPS})")
            page.screenshot(path=f"{tmp}/{i:04d}.png")
        palette = f"{tmp}/palette.png"
        subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/%04d.png",
                        "-vf", "palettegen=max_colors=128:stats_mode=diff", palette], check=True)
        subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", f"{tmp}/%04d.png",
                        "-i", palette, "-lavfi", "paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                        "-loop", "0", str(OUT / f"{name}.gif")], check=True)
    print(f"{name}.gif {size[0]}x{size[1]} {duration}s {(OUT / f'{name}.gif').stat().st_size // 1024} KB")


def main(names):
    names = names or sorted(p.stem for p in SRC.glob("*.html"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        for name in names:
            build(page, name)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
