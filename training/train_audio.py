"""Voice-emotion CNN architecture (inference-only port).

app/analysis/pipelines/voice_emotion.py loads a trained CNN-MFCC checkpoint via
`from training.train_audio import MFCCCNN`. This repo previously had no such
module, so the load always failed and voice-emotion silently fell back to the
prosody baseline. This is the minimal architecture needed to load the trained
`AI_MODELS/emotion/cnn_mfcc.pt` checkpoint (sourced from the audited external
emotion model) — only the model class, not the full training pipeline, so it
carries no dataset/HuggingFace dependencies.

The AdaptiveAvgPool2d((4, 16)) makes the network accept any MFCC time length,
so it works with this repo's AudioFeatureExtractor.mfcc_tensor output.
"""
from __future__ import annotations

from torch import nn


class MFCCCNN(nn.Module):
    def __init__(self, num_classes: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 16)),
            nn.Flatten(),
            nn.Dropout(0.25),
            nn.Linear(32 * 4 * 16, num_classes),
        )

    def forward(self, x):
        return self.net(x)
