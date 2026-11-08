"""Serve the setup page on its own for a look: python desktop/preview_setup.py PORT"""
import os
import sys
import tempfile

os.environ.setdefault("INNERBLOOM_DATA_DIR", tempfile.mkdtemp(prefix="innerbloom_setup_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desktop.launcher import build_app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(build_app(), host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 47616)
