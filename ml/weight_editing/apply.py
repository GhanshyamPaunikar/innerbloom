"""Write the fitted offsets into the model's weights: a new GGUF file.

    .venv-ml/bin/python -m ml.weight_editing.apply --gguf ~/Downloads/innerbloom-reader-1.5b-f16.gguf

The model shares one table for reading and writing tokens (token_embd). The
edit adds a separate output table (output.weight), a copy of token_embd, and
changes only the 16 rows for the emotions' first tokens:

    output[k] = token_embd[k] + offset_k * hbar / |hbar|^2

where hbar is the mean final state at the moment the model picks the emotion
(from probe.py, training entries only). At that moment the logit for emotion
k moves by about offset_k; reading is untouched because token_embd is unchanged.
"""
import argparse
import json
import sys
from pathlib import Path

import gguf
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from innerbloom_core.analysis import EMOTIONS  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    work = ROOT / "reports" / "weight_editing"
    out = args.out or args.gguf.with_name(args.gguf.stem.replace("-f16", "") + "-edited-f16.gguf")

    from transformers import AutoTokenizer
    from ml.weight_editing.probe import first_tokens
    tok = AutoTokenizer.from_pretrained(str(args.gguf.parent), gguf_file=args.gguf.name)
    ids16 = first_tokens(tok)
    offsets = json.loads((work / "offsets.json").read_text())["offsets"]
    hbar = np.load(work / "hbar.npy")
    step = hbar / (hbar @ hbar)

    reader = gguf.GGUFReader(str(args.gguf))
    arch = reader.fields["general.architecture"].contents()
    writer = gguf.GGUFWriter(str(out), arch)
    for field in reader.fields.values():
        if field.name == "general.architecture" or field.name.startswith("GGUF."):
            continue
        main_type = field.types[0]
        sub_type = field.types[-1] if main_type == gguf.GGUFValueType.ARRAY else None
        writer.add_key_value(field.name, field.contents(), main_type, sub_type=sub_type)

    changed = 0
    for t in reader.tensors:
        data = np.asarray(t.data)
        writer.add_tensor(t.name, data, raw_dtype=t.tensor_type)
        if t.name == "token_embd.weight":
            head = data.astype(np.float32).copy()
            for k, e in zip(ids16, EMOTIONS):
                if offsets[e]:
                    head[k] += offsets[e] * step
                    changed += 1
            writer.add_tensor("output.weight", head.astype(np.float16), raw_dtype=gguf.GGMLQuantizationType.F16)

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    total = len(EMOTIONS) * hbar.size
    print(f"wrote {out}: {changed} of 151,936 output rows changed "
          f"({changed * hbar.size:,} numbers, {changed * hbar.size / 1.54e9:.6%} of the model)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
