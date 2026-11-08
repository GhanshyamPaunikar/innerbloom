"""First-run setup for the desktop app: Ollama and the three models.

Served by the desktop launcher only (desktop/launcher.py), on the same
loopback-only backend as the journal. The page is desktop/setup.html.
"""
import json
import os
import platform
import threading
import webbrowser
from pathlib import Path
from typing import Dict, Optional

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import app as backend

OLLAMA_API = backend.OLLAMA_TAGS_URL.rsplit("/", 1)[0]
OLLAMA_DOWNLOAD = "https://ollama.com/download"
PAGE = Path(__file__).with_name("setup.html")
CHOICES = Path(backend.DATA_DIR) / "desktop.json"

router = APIRouter(include_in_schema=False)
_pulls: Dict[str, dict] = {}
_lock = threading.Lock()


def models() -> list:
    return [
        {"name": backend.MODEL, "source": backend.MODEL, "label": "Writing and chat",
         "about": "Talks with you about your entries and writes your insights.", "size_gb": 4.7, "required": True},
        {"name": backend.EMBED_MODEL, "source": backend.EMBED_MODEL, "label": "Memory search",
         "about": "Finds past entries by meaning, not just by words.", "size_gb": 0.7, "required": True},
        {"name": backend.DEFAULT_READER_MODEL, "source": backend.READER_SOURCE, "label": "Fast entry reader",
         "about": "Reads each entry's mood and the people in it, five times faster. Recommended.",
         "size_gb": 1.9, "required": False},
    ]


def _bare(name: str) -> str:
    return name[:-len(":latest")] if name.endswith(":latest") else name


def installed_models() -> Optional[set]:
    try:
        r = requests.get(f"{OLLAMA_API}/tags", timeout=3)
        r.raise_for_status()
        return {_bare(m.get("name", "")) for m in r.json().get("models", [])}
    except Exception:
        return None


def choices() -> dict:
    try:
        return json.loads(CHOICES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ready() -> bool:
    have = installed_models()
    if have is None:
        return False
    skipped = choices().get("skip_reader", False)
    return all(_bare(m["name"]) in have for m in models() if m["required"] or not skipped)


def _ollama_state(have: Optional[set]) -> str:
    if have is not None:
        return "running"
    from desktop.launcher import ollama_app_path
    return "installed" if ollama_app_path() else "missing"


def _pull(model: dict) -> None:
    state = _pulls[model["name"]]
    layers: Dict[str, tuple] = {}
    try:
        with requests.post(f"{OLLAMA_API}/pull", json={"model": model["source"], "stream": True},
                           stream=True, timeout=None) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                with _lock:
                    state["status"] = msg.get("status", state["status"])
                    if msg.get("total") and msg.get("digest"):  # one model is several files: add them up
                        layers[msg["digest"]] = (msg.get("completed", 0), msg["total"])
                        state["completed"] = sum(c for c, _ in layers.values())
                        state["total"] = sum(t for _, t in layers.values())
        if model["source"] != model["name"]:
            r = requests.post(f"{OLLAMA_API}/copy", json={"source": model["source"], "destination": model["name"]},
                              timeout=60)
            r.raise_for_status()
            backend._reader_cache.update(model=None, checked=0.0)  # use the new reader straight away
        with _lock:
            state.update(status="done", done=True)
    except Exception as exc:
        with _lock:
            state.update(status="failed", error=str(exc), done=True)


@router.get("/setup", response_class=HTMLResponse)
def setup_page():
    return HTMLResponse(PAGE.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/setup/status")
def setup_status():
    have = installed_models()
    out = []
    for m in models():
        with _lock:
            pull = dict(_pulls.get(m["name"], {}))
        out.append({**m, "installed": have is not None and _bare(m["name"]) in have, "pull": pull or None})
    return {"ollama": _ollama_state(have), "platform": platform.system(), "models": out,
            "skip_reader": choices().get("skip_reader", False), "ready": ready()}


@router.post("/setup/ollama/start")
def setup_start_ollama():
    from desktop.launcher import start_ollama
    return {"started": start_ollama()}


@router.post("/setup/ollama/download")
def setup_download_ollama():
    webbrowser.open(OLLAMA_DOWNLOAD)
    return {"opened": OLLAMA_DOWNLOAD}


class PullRequest(BaseModel):
    name: str


@router.post("/setup/pull")
def setup_pull(req: PullRequest):
    model = next((m for m in models() if m["name"] == req.name), None)
    if model is None:
        raise HTTPException(404, "Unknown model")
    with _lock:
        current = _pulls.get(model["name"])
        if current and not current.get("done"):
            return {"started": False}
        _pulls[model["name"]] = {"status": "starting", "completed": 0, "total": 0, "done": False}
    threading.Thread(target=_pull, args=(model,), daemon=True).start()
    return {"started": True}


class SkipRequest(BaseModel):
    skip: bool = True


@router.post("/setup/skip-reader")
def setup_skip_reader(req: SkipRequest):
    data = choices()
    data["skip_reader"] = req.skip
    CHOICES.parent.mkdir(parents=True, exist_ok=True)
    CHOICES.write_text(json.dumps(data), encoding="utf-8")
    return data
