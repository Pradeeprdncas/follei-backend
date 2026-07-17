from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass
class SpeechPreprocessor:
    target_sr: int = 16000
    vad_frame_ms: int = 30
    silence_threshold: float = 0.015
    enable_noise_reduction: bool = False
    max_audio_seconds: float | None = 120.0
    use_silero_vad: bool = True

    def load_audio(self, audio_bytes: bytes) -> Tuple[np.ndarray, int]:
        try:
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("soundfile is required to load uploaded audio") from exc
        audio, sample_rate = sf.read(io.BytesIO(audio_bytes), always_2d=False)
        audio = np.asarray(audio, dtype=np.float32)
        return audio, sample_rate

    def to_mono(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return audio
        return np.mean(audio, axis=1).astype(np.float32)

    def resample(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if sample_rate == self.target_sr:
            return audio.astype(np.float32)
        try:
            import librosa
        except ImportError as exc:
            raise RuntimeError("librosa is required for 16kHz resampling") from exc
        return librosa.resample(audio.astype(np.float32), orig_sr=sample_rate, target_sr=self.target_sr)

    def reduce_noise(self, audio: np.ndarray) -> np.ndarray:
        if not self.enable_noise_reduction:
            return audio
        try:
            import noisereduce as nr
        except ImportError:
            return audio
        return nr.reduce_noise(y=audio, sr=self.target_sr).astype(np.float32)

    def normalize(self, audio: np.ndarray) -> np.ndarray:
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak <= 1e-8:
            return audio.astype(np.float32)
        return (audio / peak).astype(np.float32)

    def vad_mask(self, audio: np.ndarray) -> np.ndarray:
        frame_length = max(1, int(self.target_sr * self.vad_frame_ms / 1000))
        mask = np.zeros_like(audio, dtype=bool)
        for start in range(0, len(audio), frame_length):
            end = min(len(audio), start + frame_length)
            frame = audio[start:end]
            rms = float(np.sqrt(np.mean(frame**2))) if frame.size else 0.0
            if rms >= self.silence_threshold:
                mask[start:end] = True
        return mask

    def remove_silence(self, audio: np.ndarray) -> np.ndarray:
        mask = self.vad_mask(audio)
        voiced_indexes = np.flatnonzero(mask)
        if not voiced_indexes.size:
            return audio.astype(np.float32)
        padding = int(self.target_sr * 0.25)
        start = max(0, int(voiced_indexes[0]) - padding)
        end = min(len(audio), int(voiced_indexes[-1]) + padding)
        return audio[start:end].astype(np.float32)

    def silero_vad(self, audio: np.ndarray) -> np.ndarray:
        try:
            import torch
            import silero_vad
            if audio.ndim > 1:
                audio = self.to_mono(audio)
            audio_float32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio
            vad_iterator = silero_vad.get_speech_timestamps(
                audio_float32,
                model=silero_vad.load_model(),
                sampling_rate=self.target_sr,
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=100,
                return_seconds=False,
            )
            if not vad_iterator:
                return audio.astype(np.float32)
            segments = []
            padding = int(self.target_sr * 0.1)
            for seg in vad_iterator:
                seg_start = max(0, seg["start"] - padding)
                seg_end = min(len(audio), seg["end"] + padding)
                segments.append(audio[seg_start:seg_end])
            return np.concatenate(segments).astype(np.float32) if segments else audio.astype(np.float32)
        except Exception:
            return self.remove_silence(audio)

    def preprocess(self, audio_bytes: bytes) -> Tuple[np.ndarray, int]:
        audio, sample_rate = self.load_audio(audio_bytes)
        audio = self.to_mono(audio)
        audio = self.resample(audio, sample_rate)
        if self.max_audio_seconds is not None:
            max_samples = int(self.target_sr * self.max_audio_seconds)
            audio = audio[:max_samples]
        audio = self.reduce_noise(audio)
        if self.use_silero_vad:
            audio = self.silero_vad(audio)
        else:
            audio = self.remove_silence(audio)
        audio = self.normalize(audio)
        return audio.astype(np.float32), self.target_sr

    def augment_time_shift(self, audio: np.ndarray, max_shift: int = 1600) -> np.ndarray:
        shift = np.random.randint(-max_shift, max_shift + 1)
        return np.roll(audio, shift).astype(np.float32)

    def augment_pitch_shift(self, audio: np.ndarray, semitones: float = 2.0) -> np.ndarray:
        try:
            import librosa
        except ImportError:
            return audio
        return librosa.effects.pitch_shift(audio, sr=self.target_sr, n_steps=semitones).astype(np.float32)

    def augment_background_noise(self, audio: np.ndarray, noise_level: float = 0.005) -> np.ndarray:
        noise = np.random.normal(0, noise_level, size=audio.shape)
        return self.normalize(audio + noise).astype(np.float32)
