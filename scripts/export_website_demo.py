"""Copy the public Innerbloom demo into the portfolio website.

    python scripts/export_website_demo.py ~/Documents/ghanshyam

Writes, inside the website project:
  public/innerbloom/        the page and its assets, served at /innerbloom
  api/_innerbloom/          the backend and the sample journal (demo_seed)
  api/innerbloom.py         the Vercel Python function behind /innerbloom/api

The website's next.config.ts rewrites /innerbloom/api/* to that function, and
GEMINI_API_KEY is set in the Vercel project's environment variables, never
in these files. Re-run after changing Innerbloom to update the demo.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ENTRY = '''"""Innerbloom public demo backend, copied from the Innerbloom repo by
scripts/export_website_demo.py. Edit it there, not here."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("INNERBLOOM_PROVIDER", "gemini")
os.environ.setdefault("INNERBLOOM_SANDBOX", "1")
os.environ.setdefault("INNERBLOOM_DATA_DIR", "/tmp/innerbloom")
os.environ.setdefault("INNERBLOOM_SEED_DIR", os.path.join(HERE, "_innerbloom", "demo_seed"))
sys.path.insert(0, os.path.join(HERE, "_innerbloom"))

from fastapi import FastAPI  # noqa: E402
from innerbloom_app import app as innerbloom  # noqa: E402

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/innerbloom/api", innerbloom)
app.mount("/api/innerbloom", innerbloom)
'''

PAGE_META = (
    '<head><base href="/innerbloom/">'
    '<meta name="innerbloom-api" content="/innerbloom/api">'
    '<meta name="innerbloom-public-demo" content="true">'
)


def main(site: Path):
    if not (site / "next.config.ts").exists():
        sys.exit(f"{site} does not look like the website project.")
    if not (ROOT / "demo_seed" / "journal.json").exists():
        sys.exit("Build the sample journal first: python scripts/build_demo_seed.py")

    page = site / "public" / "innerbloom"
    shutil.rmtree(page, ignore_errors=True)
    shutil.copytree(ROOT / "assets", page / "assets")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert html.count("<head>") == 1
    (page / "index.html").write_text(html.replace("<head>", PAGE_META, 1), encoding="utf-8")

    backend = site / "api" / "_innerbloom"
    shutil.rmtree(backend, ignore_errors=True)
    backend.mkdir(parents=True)
    shutil.copy(ROOT / "app.py", backend / "innerbloom_app.py")
    shutil.copytree(ROOT / "demo_seed", backend / "demo_seed")
    (site / "api" / "innerbloom.py").write_text(ENTRY, encoding="utf-8")
    print("Exported the Innerbloom demo to", site)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).expanduser().resolve())
