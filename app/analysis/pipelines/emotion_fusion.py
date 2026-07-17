from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class EmotionFusionResult:
    final_emotion: str
    confidence: float
    reason: str


class EmotionFusionEngine:
    text_weight: float = 0.6
    voice_weight: float = 0.4
    decisive_text_threshold: float = 0.6

    sentiment_to_emotion = {
        "positive": "happy",
        "negative": "sad",
        "neutral": "neutral",
    }

    contradiction_rules = {
        ("positive", "angry"): ("frustrated", "positive words but angry voice tone"),
        ("positive", "sad"): ("mixed", "positive text with sad vocal tone"),
        ("neutral", "sad"): ("sad", "neutral words with sad voice tone"),
        ("negative", "angry"): ("angry", "negative text reinforced by angry voice tone"),
        ("negative", "happy"): ("sarcastic_or_masked", "negative words with happy vocal tone"),
    }

    def fuse(
        self,
        text_sentiment: str,
        text_confidence: float,
        voice_emotion: str,
        voice_confidence: float,
    ) -> EmotionFusionResult:
        text_sentiment = text_sentiment.lower()
        voice_emotion = voice_emotion.lower()
        if (text_sentiment, voice_emotion) in self.contradiction_rules:
            emotion, reason = self.contradiction_rules[(text_sentiment, voice_emotion)]
            confidence = round((text_confidence * self.text_weight) + (voice_confidence * self.voice_weight), 6)
            return EmotionFusionResult(emotion, confidence, reason)

        text_emotion = self.sentiment_to_emotion.get(text_sentiment, "neutral")
        if voice_emotion == "neutral" and text_emotion != "neutral" and text_confidence >= self.decisive_text_threshold:
            confidence = round(min(text_confidence * 0.85 + voice_confidence * 0.15, 1.0), 6)
            return EmotionFusionResult(
                final_emotion=text_emotion,
                confidence=confidence,
                reason=(
                    f"text sentiment is confidently {text_sentiment}; neutral voice is treated "
                    "as no strong conflicting vocal emotion"
                ),
            )

        if text_emotion == "neutral" and voice_emotion != "neutral":
            confidence = round(min(voice_confidence * 0.85 + text_confidence * 0.15, 1.0), 6)
            return EmotionFusionResult(
                final_emotion=voice_emotion,
                confidence=confidence,
                reason=f"neutral text with clear {voice_emotion} vocal tone",
            )

        scores: Dict[str, float] = {
            text_emotion: text_confidence * self.text_weight,
            voice_emotion: voice_confidence * self.voice_weight,
        }
        if text_emotion == voice_emotion:
            scores[text_emotion] = text_confidence * self.text_weight + voice_confidence * self.voice_weight
        final = max(scores, key=scores.get)
        confidence = round(min(scores[final], 1.0), 6)
        return EmotionFusionResult(
            final_emotion=final,
            confidence=confidence,
            reason=f"weighted fusion selected {final} from text={text_sentiment} and voice={voice_emotion}",
        )
