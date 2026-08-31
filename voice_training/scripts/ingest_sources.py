#!/usr/bin/env python3
"""Ingest owned/licensed sources and standardize them for human review."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def run(command: list[str], dry_run: bool) -> None:
    print(" ".join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--separate-vocals", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required")
    if args.separate_vocals and not shutil.which("python"):
        raise RuntimeError("python is required for Demucs")

    raw_dir = args.output_dir / "raw"
    standardized_dir = args.output_dir / "standardized"
    raw_dir.mkdir(parents=True, exist_ok=True)
    standardized_dir.mkdir(parents=True, exist_ok=True)

    for line_number, raw in enumerate(args.manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        item = json.loads(raw)
        if item.get("rights_confirmed") is not True:
            raise ValueError(f"line {line_number}: source rights are not confirmed")
        source_id = str(item["source_id"]).strip()
        if not source_id or "/" in source_id or "\\" in source_id:
            raise ValueError(f"line {line_number}: source_id must be a plain identifier")
        raw_audio = raw_dir / f"{source_id}.wav"
        url = str(item.get("url", "")).strip()
        local_path = Path(str(item.get("local_path", ""))).expanduser()
        if url:
            if not shutil.which("yt-dlp"):
                raise RuntimeError("yt-dlp is required for URL sources")
            run(
                [
                    "yt-dlp", "--no-playlist", "-x", "--audio-format", "wav",
                    "--audio-quality", "0", "-o", str(raw_audio), url,
                ],
                args.dry_run,
            )
        elif local_path.is_file():
            run(["ffmpeg", "-y", "-i", str(local_path), str(raw_audio)], args.dry_run)
        else:
            raise ValueError(f"line {line_number}: provide an existing local_path or URL")

        standardized = standardized_dir / f"{source_id}.wav"
        run(
            [
                "ffmpeg", "-y", "-i", str(raw_audio), "-ac", "1", "-ar", "24000",
                "-sample_fmt", "s16", str(standardized),
            ],
            args.dry_run,
        )
        if args.separate_vocals:
            run(
                [
                    "python", "-m", "demucs", "--two-stems=vocals", "-o",
                    str(args.output_dir / "separated"), str(standardized),
                ],
                args.dry_run,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
