from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def split_on_silence(
    audio: np.ndarray,
    sample_rate: int = 16000,
    min_silence_len_ms: int = 500,
    silence_thresh: float = 0.02,
    min_chunk_len_ms: int = 1000,
    max_chunk_len_ms: int = 30000,
    keep_silence_ms: int = 200,
) -> List[Tuple[int, int, np.ndarray]]:
    """Split audio into chunks at silence boundaries.

    Returns list of (start_sample, end_sample, chunk_audio) tuples.
    """
    if len(audio) == 0:
        return []

    frame_ms = 10
    frame_len = int(sample_rate * frame_ms / 1000)
    silence_frames_needed = max(1, min_silence_len_ms // frame_ms)

    rms_per_frame = []
    for i in range(0, len(audio), frame_len):
        frame = audio[i:i + frame_len]
        rms = float(np.sqrt(np.mean(frame ** 2))) if frame.size > 0 else 0.0
        rms_per_frame.append(rms)

    is_silent = [r < silence_thresh for r in rms_per_frame]

    # Find silence regions
    regions: List[Tuple[int, int]] = []
    in_silence = False
    start_frame = 0
    for i, silent in enumerate(is_silent):
        if silent and not in_silence:
            in_silence = True
            start_frame = i
        elif not silent and in_silence:
            if i - start_frame >= silence_frames_needed:
                regions.append((start_frame, i))
            in_silence = False
    if in_silence and len(is_silent) - start_frame >= silence_frames_needed:
        regions.append((start_frame, len(is_silent)))

    if not regions:
        return [(0, len(audio), audio)]

    keep_samples = int(sample_rate * keep_silence_ms / 1000)

    # Build chunks from non-silent regions
    chunks: List[Tuple[int, int, np.ndarray]] = []
    prev_end = 0
    for sil_start, sil_end in regions:
        seg_start_frame = prev_end
        seg_end_frame = sil_start

        start_sample = seg_start_frame * frame_len
        end_sample = min(seg_end_frame * frame_len, len(audio))

        if end_sample - start_sample >= int(sample_rate * min_chunk_len_ms / 1000):
            # Add padding
            padded_start = max(0, start_sample - keep_samples)
            padded_end = min(len(audio), end_sample + keep_samples)
            chunks.append((padded_start, padded_end, audio[padded_start:padded_end]))

        prev_end = sil_end

    # Last segment
    start_sample = prev_end * frame_len
    if len(audio) - start_sample >= int(sample_rate * min_chunk_len_ms / 1000):
        padded_start = max(0, start_sample - keep_samples)
        chunks.append((padded_start, len(audio), audio[padded_start:]))

    # Merge tiny adjacent chunks
    merged: List[Tuple[int, int, np.ndarray]] = []
    i = 0
    while i < len(chunks):
        start_s, end_s, chunk = chunks[i]
        j = i + 1
        while j < len(chunks):
            gap = chunks[j][0] - end_s
            if gap < int(sample_rate * 0.3) and (chunks[j][1] - start_s) <= int(sample_rate * max_chunk_len_ms / 1000):
                end_s = chunks[j][1]
                chunk = audio[start_s:end_s]
                j += 1
            else:
                break
        merged.append((start_s, end_s, chunk))
        i = j

    if not merged:
        return [(0, len(audio), audio)]

    return merged
