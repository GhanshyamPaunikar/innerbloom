"""Write the production analysis spec, read from the code, never retyped.

    python -m ml.spec            # writes ml/datasets/production_spec.json
    python -m ml.spec --check    # fails if the file is out of date

The benchmark compares against this file, so a change to the prompt, the
emotion list or the default model shows up as a change here.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT / "ml" / "datasets" / "production_spec.json"
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402

# Only the prompt's fixed parts are hashed: the entry text is substituted in.
_PLACEHOLDER = "<<ENTRY>>"


def build() -> dict:
    # app.py holds the provider defaults; import it against an empty data folder.
    os.environ.setdefault("INNERBLOOM_DATA_DIR", tempfile.mkdtemp(prefix="innerbloom_spec_"))
    for name in ("INNERBLOOM_MODEL", "INNERBLOOM_PROVIDER", "INNERBLOOM_EMBED_MODEL"):
        os.environ.pop(name, None)
    import app  # noqa: E402

    template = analysis.build_prompt(_PLACEHOLDER)
    return {
        "source": "innerbloom_core/analysis.py and app.py defaults",
        "model": app.MODEL,
        "provider": app.PROVIDER,
        "embed_model": app.EMBED_MODEL,
        "temperature": analysis.TEMPERATURE,
        "emotions": list(analysis.EMOTIONS),
        "fields": {
            "emotion": "one of emotions; anything else becomes 'neutral'",
            "intensity": "integer clamped to 1-10; unreadable becomes 5",
            "summary": "string, cut to 280 characters",
            "tags": "up to 5 lowercase [a-z0-9-] words, each cut to 24 characters",
            "themes": "up to 3 strings, each cut to 40 characters",
            "people": "up to 6 names, letters/space/-/'/. only, 40 characters max, case-insensitive de-duplication",
        },
        "failure": "no JSON object or no 'emotion' key: placeholders plus analysis_status 'failed'",
        "prompt_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "prompt_template": template,
    }


def main(argv) -> int:
    spec = build()
    text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    if "--check" in argv:
        current = SPEC_FILE.read_text(encoding="utf-8") if SPEC_FILE.exists() else ""
        if current != text:
            print("ml/datasets/production_spec.json is out of date: run python -m ml.spec")
            return 1
        print("production spec is current")
        return 0
    SPEC_FILE.write_text(text, encoding="utf-8")
    print(f"wrote {SPEC_FILE.relative_to(ROOT)} (prompt {spec['prompt_sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
