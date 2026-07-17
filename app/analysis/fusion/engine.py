"""Emotion fusion engine — combines sentiment + emotion with contradiction handling.

Produces a single fused result with explanatory reason.
"""
from dataclasses import dataclass


@dataclass
class FusionResult:
    final_emotion: str
    confidence: float
    reason: str


def fuse(sentiment: dict | None, emotion: dict | None) -> FusionResult:
    """Combine sentiment and emotion into a single fused analysis.

    Contradiction rules:
      - positive + angry       → frustrated
      - positive + sad         → mixed
      - neutral  + sad         → sad
      - negative + angry       → angry
      - negative + happy       → sarcastic_or_masked
      - neutral emotion        → sentiment label wins
      - neutral sentiment      → emotion label wins
    """
    if not sentiment and not emotion:
        return FusionResult(final_emotion="neutral", confidence=0.0, reason="no data")

    if not sentiment:
        return FusionResult(
            final_emotion=emotion.get("overall", "neutral"),
            confidence=emotion.get("overall_confidence", 0.5),
            reason="emotion only",
        )

    if not emotion:
        return FusionResult(
            final_emotion=sentiment.get("overall", "neutral"),
            confidence=sentiment.get("overall_confidence", 0.5),
            reason="sentiment only",
        )

    sent_label = sentiment.get("overall", "neutral").lower()
    emo_label = emotion.get("overall", "neutral").lower()
    sent_conf = sentiment.get("overall_confidence", 0.5)
    emo_conf = emotion.get("overall_confidence", 0.5)

    # Contradiction rules
    rules = {
        ("positive", "angry"): ("frustrated", sent_conf),
        ("positive", "sad"): ("mixed", emo_conf),
        ("neutral", "sad"): ("sad", emo_conf),
        ("negative", "angry"): ("angry", emo_conf),
        ("negative", "happy"): ("sarcastic_or_masked", emo_conf),
    }

    key = (sent_label, emo_label)
    if key in rules:
        final_label, confidence = rules[key]
        reason = f"contradiction: {sent_label}(text) + {emo_label}(voice) → {final_label}"
        return FusionResult(final_emotion=final_label, confidence=confidence, reason=reason)

    # No contradiction — weighted score
    if emo_label == "neutral":
        return FusionResult(
            final_emotion=sent_label,
            confidence=sent_conf,
            reason=f"emotion was neutral, sentiment ({sent_label}) wins",
        )
    if sent_label == "neutral":
        return FusionResult(
            final_emotion=emo_label,
            confidence=emo_conf,
            reason=f"sentiment was neutral, emotion ({emo_label}) wins",
        )

    # Weighted average preferring higher confidence
    if sent_conf >= emo_conf:
        return FusionResult(
            final_emotion=sent_label,
            confidence=sent_conf,
            reason=f"sentiment ({sent_label}) with weight {sent_conf:.2f} > emotion ({emo_label}) weight {emo_conf:.2f}",
        )
    return FusionResult(
        final_emotion=emo_label,
        confidence=emo_conf,
        reason=f"emotion ({emo_label}) with weight {emo_conf:.2f} > sentiment ({sent_label}) weight {sent_conf:.2f}",
    )
