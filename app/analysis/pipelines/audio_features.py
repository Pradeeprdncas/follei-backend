from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class AudioFeatureExtractor:
    sample_rate: int = 16000
    n_mfcc: int = 40
    n_mels: int = 64

    def extract(self, audio: np.ndarray) -> Dict[str, np.ndarray | float]:
        try:
            import librosa
        except ImportError as exc:
            raise RuntimeError("librosa is required for audio feature extraction") from exc

        mfcc = librosa.feature.mfcc(y=audio, sr=self.sample_rate, n_mfcc=self.n_mfcc)
        mel = librosa.feature.melspectrogram(y=audio, sr=self.sample_rate, n_mels=self.n_mels)
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=self.sample_rate)
        spectral_contrast = librosa.feature.spectral_contrast(y=audio, sr=self.sample_rate)
        chroma = librosa.feature.chroma_stft(y=audio, sr=self.sample_rate)
        zcr = librosa.feature.zero_crossing_rate(audio)
        rms = librosa.feature.rms(y=audio)
        tempo = librosa.beat.tempo(y=audio, sr=self.sample_rate)
        pitch = librosa.yin(audio, fmin=50, fmax=500, sr=self.sample_rate)
        energy = np.sum(audio**2) / max(len(audio), 1)

        return {
            "mfcc": mfcc,
            "delta_mfcc": librosa.feature.delta(mfcc),
            "delta_delta_mfcc": librosa.feature.delta(mfcc, order=2),
            "mel_spectrogram": mel,
            "pitch": pitch,
            "energy": float(energy),
            "spectral_centroid": spectral_centroid,
            "spectral_contrast": spectral_contrast,
            "chroma": chroma,
            "zero_crossing_rate": zcr,
            "rms_energy": rms,
            "tempo": float(tempo[0]) if len(tempo) else 0.0,
        }

    def mfcc_tensor(self, audio: np.ndarray, max_frames: int = 256) -> np.ndarray:
        features = self.extract(audio)
        mfcc = np.asarray(features["mfcc"], dtype=np.float32)
        if mfcc.shape[1] < max_frames:
            pad = max_frames - mfcc.shape[1]
            mfcc = np.pad(mfcc, ((0, 0), (0, pad)))
        return mfcc[:, :max_frames]

    @staticmethod
    def math_explanations() -> Dict[str, str]:
        return {
            "MFCC": "Cepstral coefficients computed from log Mel filterbank energies using a discrete cosine transform.",
            "Delta MFCC": "First temporal derivative of MFCCs, approximating speech dynamics over time.",
            "Delta-Delta MFCC": "Second temporal derivative of MFCCs, representing acceleration in spectral movement.",
            "Mel Spectrogram": "Short-time power spectrum projected onto the Mel scale.",
            "Pitch": "Estimated fundamental frequency F0, the perceived voice tone.",
            "Energy": "Mean squared signal amplitude, E = sum(x[n]^2) / N.",
            "Spectral Centroid": "Weighted mean of frequency bins, sum(f * magnitude) / sum(magnitude).",
            "Spectral Contrast": "Difference between spectral peaks and valleys in each frequency band.",
            "Chroma": "Energy mapped into 12 pitch classes independent of octave.",
            "Zero Crossing Rate": "Rate at which the waveform changes sign.",
            "RMS Energy": "Root mean square amplitude, sqrt(mean(x[n]^2)).",
            "Tempo": "Estimated beats per minute from onset strength patterns.",
        }
