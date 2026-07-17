from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np

from app.analysis.pipelines.audio_features import AudioFeatureExtractor

logger = logging.getLogger(__name__)


@dataclass
class VoiceEmotionResult:
    emotion: str
    confidence: float
    probabilities: Dict[str, float]
    model: str
    inference_time_ms: float
    memory_mb: float | None = None


class VoiceEmotionRecognizer:
    """Production inference wrapper for CNN-MFCC or Wav2Vec2 emotion models.

    The class first attempts to load a trained CNN-MFCC checkpoint produced by
    `training/train_audio.py`. If no trained checkpoint is present, it returns a
    deterministic acoustic baseline so the API remains available during
    development and CI.
    """

    labels = ["angry", "happy", "neutral", "sad"]

    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.model_path = Path(model_path)
        self.sample_rate = sample_rate
        self.extractor = AudioFeatureExtractor(sample_rate=sample_rate)
        self.model = None
        self.device = "cpu"

    def initialize(self) -> None:
        if self.model is not None:
            return
        if not self.model_path.exists():
            logger.warning("Voice emotion model not found at %s; using acoustic baseline", self.model_path)
            return
        try:
            import torch

            from training.train_audio import MFCCCNN

            checkpoint = torch.load(self.model_path, map_location="cpu")
            self.labels = list(checkpoint.get("labels", self.labels))
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = MFCCCNN(num_classes=len(self.labels))
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.to(self.device)
            self.model.eval()
            logger.info("Loaded CNN-MFCC emotion model from %s on %s", self.model_path, self.device)
        except Exception as exc:
            logger.warning("Failed to load CNN-MFCC emotion model: %s; using acoustic baseline", exc)
            self.model = None

    def predict(self, audio: np.ndarray) -> VoiceEmotionResult:
        start = time.perf_counter()
        self.initialize()
        if self.model is None:
            return self._baseline_predict(audio, start)
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch is required for voice emotion inference") from exc

        mfcc = self.extractor.mfcc_tensor(audio)
        tensor = torch.tensor(mfcc, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            logits = self.model(tensor)
            probabilities_raw = torch.softmax(logits, dim=-1).detach().cpu().numpy()[0]
        model_probabilities = {
            self._normalize_label(label): float(prob)
            for label, prob in zip(self.labels, probabilities_raw)
        }
        acoustic_probabilities = self._acoustic_probabilities(audio)
        probabilities = self._blend_probabilities(model_probabilities, acoustic_probabilities)
        emotion = max(probabilities, key=probabilities.get)
        return VoiceEmotionResult(
            emotion=emotion,
            confidence=probabilities[emotion],
            probabilities={label: round(value, 6) for label, value in probabilities.items()},
            model="hybrid_cnn_mfcc_prosody",
            inference_time_ms=round((time.perf_counter() - start) * 1000, 3),
            memory_mb=self._memory_mb(),
        )

    def _baseline_predict(self, audio: np.ndarray, start: float) -> VoiceEmotionResult:
        probabilities = self._acoustic_probabilities(audio)
        emotion = max(probabilities, key=probabilities.get)
        return VoiceEmotionResult(
            emotion=emotion,
            confidence=round(probabilities[emotion], 6),
            probabilities={label: round(value, 6) for label, value in probabilities.items()},
            model="prosody_baseline",
            inference_time_ms=round((time.perf_counter() - start) * 1000, 3),
            memory_mb=self._memory_mb(),
        )

    def _acoustic_probabilities(self, audio: np.ndarray) -> Dict[str, float]:
        features = self.extractor.extract(audio)
        energy = float(features["energy"])
        pitch = np.asarray(features["pitch"], dtype=np.float32)
        pitch = pitch[np.isfinite(pitch)]
        pitch_mean = float(np.mean(pitch)) if pitch.size else 0.0
        pitch_std = float(np.std(pitch)) if pitch.size else 0.0
        zcr = float(np.mean(features["zero_crossing_rate"]))
        rms = float(np.mean(features["rms_energy"]))
        centroid = float(np.mean(features["spectral_centroid"]))

        energetic = min(1.0, energy * 16.0 + rms * 2.5)
        bright = min(1.0, centroid / 3500.0)
        expressive_pitch = min(1.0, pitch_std / 65.0)
        high_pitch = min(1.0, max(pitch_mean - 135.0, 0.0) / 170.0)
        roughness = min(1.0, zcr * 7.0)
        low_energy = max(0.0, 1.0 - energetic)
        low_pitch = min(1.0, max(170.0 - pitch_mean, 0.0) / 170.0) if pitch_mean else 0.4

        happy = 0.10 + 0.34 * energetic + 0.24 * expressive_pitch + 0.18 * high_pitch + 0.14 * bright
        angry = 0.05 + 0.42 * energetic + 0.25 * roughness + 0.20 * bright + 0.08 * expressive_pitch
        sad = 0.08 + 0.42 * low_energy + 0.28 * low_pitch + 0.22 * (1.0 - expressive_pitch)
        neutral = 0.26 + 0.30 * (1.0 - abs(energetic - 0.5)) + 0.22 * (1.0 - expressive_pitch)
        scores = {
            "angry": max(0.0, angry),
            "happy": max(0.0, happy),
            "sad": max(0.0, sad),
            "neutral": max(0.0, neutral),
        }
        total = sum(scores.values()) or 1.0
        return {label: value / total for label, value in scores.items()}

    def _blend_probabilities(
        self,
        model_probabilities: Dict[str, float],
        acoustic_probabilities: Dict[str, float],
    ) -> Dict[str, float]:
        labels = {"angry", "happy", "neutral", "sad"}
        blended = {}
        for label in labels:
            model_value = model_probabilities.get(label, 0.0)
            acoustic_value = acoustic_probabilities.get(label, 0.0)
            blended[label] = 0.45 * model_value + 0.55 * acoustic_value

        top_acoustic = max(acoustic_probabilities, key=acoustic_probabilities.get)
        if top_acoustic != "neutral" and acoustic_probabilities[top_acoustic] >= 0.30:
            blended[top_acoustic] += 0.12
            blended["neutral"] *= 0.72

        total = sum(blended.values()) or 1.0
        return {label: round(value / total, 6) for label, value in blended.items()}

    @staticmethod
    def _normalize_label(label: str) -> str:
        normalized = label.lower()
        return {
            "positive": "happy",
            "negative": "sad",
            "frustrated": "angry",
        }.get(normalized, normalized)

    @staticmethod
    def _memory_mb() -> float | None:
        try:
            import psutil
        except ImportError:
            return None
        process = psutil.Process()
        return round(process.memory_info().rss / (1024 * 1024), 3)


def supported_emotions() -> List[str]:
    return list(VoiceEmotionRecognizer.labels)
