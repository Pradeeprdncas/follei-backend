#!/usr/bin/env python3
"""Validate provenance and audio quality before preparing a TTS dataset."""
from __future__ import annotations

import argparse
import json
import sys
import wave
from collections import Counter
from pathlib import Path


REQUIRED = {"audio", "text", "speaker", "language", "split", "source_id", "rights_confirmed"}
VALID_SPLITS = {"train", "validation", "test"}


def validate(path: Path, min_seconds: float, max_seconds: float) -> list[str]:
    errors: list[str] = []
    splits: Counter[str] = Counter()
    seen_audio: set[Path] = set()
    total_seconds = 0.0

    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        missing = REQUIRED - item.keys()
        if missing:
            errors.append(f"line {line_number}: missing fields {sorted(missing)}")
            continue
        if item["rights_confirmed"] is not True:
            errors.append(f"line {line_number}: rights_confirmed must be true")
        if item["split"] not in VALID_SPLITS:
            errors.append(f"line {line_number}: invalid split {item['split']!r}")
        if not str(item["text"]).strip():
            errors.append(f"line {line_number}: transcript is empty")

        audio_path = Path(item["audio"]).expanduser().resolve()
        if audio_path in seen_audio:
            errors.append(f"line {line_number}: duplicate audio {audio_path}")
        seen_audio.add(audio_path)
        if not audio_path.is_file():
            errors.append(f"line {line_number}: audio not found: {audio_path}")
            continue
        try:
            with wave.open(str(audio_path), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
                if wav.getnchannels() != 1:
                    errors.append(f"line {line_number}: audio must be mono")
                if wav.getframerate() != 24000:
                    errors.append(f"line {line_number}: expected 24000 Hz, got {wav.getframerate()}")
                if wav.getsampwidth() != 2:
                    errors.append(f"line {line_number}: expected 16-bit PCM WAV")
        except (wave.Error, EOFError) as exc:
            errors.append(f"line {line_number}: unreadable PCM WAV: {exc}")
            continue
        if not min_seconds <= duration <= max_seconds:
            errors.append(
                f"line {line_number}: duration {duration:.2f}s outside "
                f"{min_seconds:.1f}-{max_seconds:.1f}s"
            )
        total_seconds += duration
        splits[item["split"]] += 1

    if not seen_audio:
        errors.append("manifest contains no clips")
    if seen_audio and not {"train", "validation", "test"}.issubset(splits):
        errors.append("manifest must contain train, validation, and test clips")

    print(f"clips={len(seen_audio)} hours={total_seconds / 3600:.2f} splits={dict(splits)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--min-seconds", type=float, default=2.0)
    parser.add_argument("--max-seconds", type=float, default=12.0)
    args = parser.parse_args()
    errors = validate(args.manifest, args.min_seconds, args.max_seconds)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
