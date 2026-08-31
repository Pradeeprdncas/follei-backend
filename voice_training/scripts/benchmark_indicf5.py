#!/usr/bin/env python3
"""Generate a fixed Tamil evaluation set with the official IndicF5 interface."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from transformers import AutoModel


DEFAULT_MODEL = "ai4bharat/IndicF5"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-audio", type=Path, required=True)
    parser.add_argument("--reference-text", required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision", required=True, help="Pinned Hub commit SHA")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(
        args.model,
        revision=args.revision,
        trust_remote_code=True,
    )
    report = []
    for index, raw in enumerate(args.prompts.read_text(encoding="utf-8").splitlines()):
        if not raw.strip():
            continue
        item = json.loads(raw)
        started = time.perf_counter()
        audio = np.asarray(
            model(item["text"], ref_audio_path=str(args.reference_audio), ref_text=args.reference_text),
            dtype=np.float32,
        )
        if np.max(np.abs(audio), initial=0) > 1.0:
            audio = audio / 32768.0
        output = args.output_dir / f"{index:03d}_{item['id']}.wav"
        sf.write(output, audio, 24000)
        duration = len(audio) / 24000
        elapsed = time.perf_counter() - started
        report.append({**item, "audio": str(output), "seconds": duration, "latency": elapsed, "rtf": elapsed / duration})
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"generated {len(report)} samples in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
