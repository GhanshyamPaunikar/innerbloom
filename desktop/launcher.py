"""Innerbloom as a desktop app: one window, no terminal.

    python desktop/launcher.py            # run from a checkout
    (packaged by desktop/build.py into Innerbloom.app / Innerbloom.exe)

Starts the journal backend on this computer only, then opens it in its own
window. On first run, or whenever Ollama or a model is missing, the window
opens on a setup page (desktop/setup.html) that installs what is needed.

The journal is kept in the user's own folder, not inside the app:
  macOS    ~/Library/Application Support/Innerbloom
  Windows  %APPDATA%\\Innerbloom
  Linux    ~/.local/share/Innerbloom
"""
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # bundle or checkout root
sys.path.insert(0, str(HERE))
PORT = 47615  # fixed, so the window's saved settings (stored per address) survive restarts
OLLAMA = "http://127.0.0.1:11434"


def data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Innerbloom"


def free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 20)]:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ollama_app_path():
    """Where Ollama's own app is installed, or None."""
    system = platform.system()
    if system == "Darwin":
        for p in (Path("/Applications/Ollama.app"), Path.home() / "Applications" / "Ollama.app"):
            if p.exists():
                return p
    elif system == "Windows":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"
        if p.exists():
            return p
    import shutil
    found = shutil.which("ollama")
    return Path(found) if found else None


def start_ollama() -> bool:
    """Start Ollama if it is installed but not running. True if a start was attempted."""
    path = ollama_app_path()
    if path is None:
        return False
    flags = {"creationflags": 0x08000000} if platform.system() == "Windows" else {}  # no console window
    if platform.system() == "Darwin" and path.suffix == ".app":
        subprocess.Popen(["open", "-g", "-a", str(path)])
    elif path.name == "ollama app.exe":
        subprocess.Popen([str(path)], **flags)
    else:
        subprocess.Popen([str(path), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    return True


def build_app():
    os.environ.setdefault("INNERBLOOM_DATA_DIR", str(data_dir()))
    from app import app  # noqa: E402  (reads INNERBLOOM_DATA_DIR on import)
    from desktop.setup_routes import router
    app.include_router(router)
    return app


def serve(app, port: int) -> None:
    import uvicorn
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 30
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError("Innerbloom's backend did not start")


def main() -> int:
    from desktop.setup_routes import ready
    app = build_app()
    port = free_port(PORT)
    serve(app, port)
    start = "/app" if ready() else "/setup"
    url = f"http://127.0.0.1:{port}{start}"
    if os.environ.get("INNERBLOOM_SMOKE_TEST") == "1":  # used by the build: start, check the pages, quit
        import requests
        pages = {p: requests.get(f"http://127.0.0.1:{port}{p}", timeout=10).status_code
                 for p in ("/app", "/setup", "/setup/status", "/assets/base.css")}
        print("smoke test", pages, flush=True)
        return 0 if set(pages.values()) == {200} else 1
    try:
        import webview
    except ImportError:
        webview = None
    if webview is not None:
        try:
            webview.create_window("Innerbloom", url, width=1280, height=840, min_size=(900, 600))
            webview.start()
            return 0
        except Exception as exc:  # no system web view (e.g. WebView2 missing): fall back to the browser
            print(f"window failed ({exc}); opening in the browser", file=sys.stderr)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
