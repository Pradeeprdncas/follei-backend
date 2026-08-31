#!/usr/bin/env python3
"""Export an approved JSONL clip manifest to F5-TTS's custom CSV format."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--split", default="train", choices=("train", "validation", "test"))
    args = parser.parse_args()
    rows = []
    for line_number, raw in enumerate(args.manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        item = json.loads(raw)
        if item.get("split") != args.split:
            continue
        if item.get("rights_confirmed") is not True:
            raise ValueError(f"line {line_number}: unapproved source")
        audio = Path(item["audio"]).expanduser().resolve()
        if not audio.is_file():
            raise FileNotFoundError(audio)
        rows.append((str(audio), str(item["text"]).strip()))
    if not rows:
        raise ValueError(f"no {args.split} rows found")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="|", lineterminator="\n")
        writer.writerow(("audio_file", "text"))
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
