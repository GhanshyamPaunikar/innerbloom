"""Install Innerbloom's entry reader into Ollama.

    python scripts/get_reader.py

Downloads the reader from Hugging Face through Ollama (1.9 GB, once) and
names it innerbloom-reader:1.5b-q8-edited, the name Innerbloom looks for.
Innerbloom then reads entries with it within five minutes, no restart.
Needs Ollama running. Details: release/reader/README.md.
"""
import json
import os
import sys

import requests

READER_REPO = "gwagon63/innerbloom-reader-1.5b-GGUF"
SOURCE = f"hf.co/{READER_REPO}:Q8_0"
NAME = "innerbloom-reader:1.5b-q8-edited"
API = os.environ.get("INNERBLOOM_OLLAMA_TAGS_URL", "http://localhost:11434/api/tags").rsplit("/", 1)[0]


def installed() -> set:
    r = requests.get(f"{API}/tags", timeout=5)
    return {m.get("name", "") for m in r.json().get("models", [])}


def main() -> int:
    try:
        have = installed()
    except requests.RequestException:
        print("Ollama isn't running. Start it (open the Ollama app, or run `ollama serve`) and try again.")
        return 1
    if NAME in have:
        print(f"{NAME} is already installed. Nothing to do.")
        return 0
    print(f"Downloading {SOURCE} (1.9 GB)...")
    last = ""
    with requests.post(f"{API}/pull", json={"model": SOURCE, "stream": True}, stream=True, timeout=None) as r:
        for line in r.iter_lines():
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("error"):
                print(f"\nDownload failed: {msg['error']}")
                return 1
            status = msg.get("status", "")
            if msg.get("total"):
                status = f"{status} {100 * msg.get('completed', 0) // msg['total']}%"
            if status != last:
                print(f"\r{status:<60}", end="", flush=True)
                last = status
    print()
    r = requests.post(f"{API}/copy", json={"source": SOURCE, "destination": NAME}, timeout=60)
    if r.status_code != 200:
        print(f"Downloaded, but naming it failed ({r.status_code}). Run: ollama cp {SOURCE} {NAME}")
        return 1
    print(f"Installed as {NAME}. Innerbloom will use it for reading entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
