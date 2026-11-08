"""Bundle the entry reader for Hugging Face, and upload it when asked.

    python scripts/release_reader.py                 # stage the folder only
    python scripts/release_reader.py --upload        # stage, then upload with `hf upload`

Stages, in the folder given by --out (default ~/Downloads/innerbloom-reader-release):
  innerbloom-reader-1.5b-Q8_0.gguf   the exact file Ollama runs as innerbloom-reader:1.5b-q8-edited
  README.md, template, system, params  from release/reader/; Ollama reads the last three
                                       when it pulls from Hugging Face, so the chat format
                                       and settings match what was tested
The model file is never committed to git. Uploading needs `hf auth login` first.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from get_reader import NAME, READER_REPO  # noqa: E402

KIT = ROOT / "release" / "reader"
GGUF_NAME = "innerbloom-reader-1.5b-Q8_0.gguf"


def model_blob() -> Path:
    out = subprocess.run(["ollama", "show", NAME, "--modelfile"], capture_output=True, text=True, check=True).stdout
    return Path(re.search(r"^FROM (\S+)", out, re.M).group(1))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path.home() / "Downloads" / "innerbloom-reader-release")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    blob = model_blob()
    with blob.open("rb") as f:
        magic = f.read(4)
    if magic != b"GGUF":
        print(f"{blob} is not a GGUF file")
        return 1
    target = args.out / GGUF_NAME
    if not target.exists() or target.stat().st_size != blob.stat().st_size:
        shutil.copyfile(blob, target)
    digest = sha256(target)
    if blob.name != f"sha256-{digest}":
        print(f"copy does not match Ollama's file ({digest})")
        return 1
    for name in ("template", "system", "params"):
        shutil.copyfile(KIT / name, args.out / name)
    (args.out / "README.md").write_text((KIT / "README.md").read_text(encoding="utf-8").replace("{REPO}", READER_REPO),
                                        encoding="utf-8")
    print(f"staged {args.out}\n  {GGUF_NAME}: {target.stat().st_size / 1e9:.2f} GB, sha256 {digest}")

    if args.upload:
        hf = shutil.which("hf") or str(ROOT / ".venv-ml" / "bin" / "hf")
        cmd = [hf, "upload", READER_REPO, str(args.out), ".", "--repo-type", "model",
               "--commit-message", "Innerbloom reader 1.5B, Q8_0"]
        print("running:", " ".join(cmd))
        return subprocess.run(cmd).returncode
    print(f"to publish: python scripts/release_reader.py --upload   (repo {READER_REPO})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
