from __future__ import annotations

from app.analysis.pipelines.voice_emotion import VoiceEmotionRecognizer, VoiceEmotionResult

from app.config.settings import get_settings

_settings = get_settings()

_VOICE_EMOTION_MODEL_PATH: str = getattr(
    _settings, "voice_emotion_model_path", "AI_MODELS/emotion/cnn_mfcc.pt"
)
_AUDIO_SAMPLE_RATE: int = getattr(_settings, "audio_sample_rate", 16000)


class VoiceEmotionService:
    recognizer: VoiceEmotionRecognizer | None = None

    @classmethod
    def initialize(cls) -> None:
        if cls.recognizer is None:
            cls.recognizer = VoiceEmotionRecognizer(
                model_path=_VOICE_EMOTION_MODEL_PATH,
                sample_rate=_AUDIO_SAMPLE_RATE,
            )
        cls.recognizer.initialize()

    @classmethod
    def predict(cls, audio) -> VoiceEmotionResult:
        if cls.recognizer is None:
            cls.initialize()
        return cls.recognizer.predict(audio)
