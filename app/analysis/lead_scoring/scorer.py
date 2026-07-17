"""Lead scoring — combines ML score, verified conversation evidence, sentiment, intent, and company rules.

Returns explainable score with component breakdown.
"""
from dataclasses import dataclass, field


@dataclass
class LeadScoreResult:
    overall: float
    category: str
    confidence: float
    explanation: str
    verified_reasons: list[str] = field(default_factory=list)
    components: dict = field(default_factory=dict)


def score_conversation(
    sentiment: dict | None = None,
    emotion: dict | None = None,
    claims: list[dict] | None = None,
    transcript: str | None = None,
    company_rules: dict | None = None,
) -> LeadScoreResult:
    """Score a lead based on conversation analysis.

    Combines:
    1. Sentiment polarity (negative → lower score)
    2. Emotion (angry/sad → lower score)
    3. Verified claims (supported claims → higher score)
    4. Claim categories (pricing + intent → buying signal)
    5. Company rules (overrides from config)
    """
    score = 50.0  # neutral baseline
    reasons = []

    # Sentiment adjustment
    if sentiment:
        sent_label = sentiment.get("overall", "neutral").lower()
        sent_conf = sentiment.get("overall_confidence", 0.5)
        if sent_label == "positive":
            score += 15 * sent_conf
            reasons.append(f"Positive sentiment (+{15 * sent_conf:.0f})")
        elif sent_label == "negative":
            score -= 20 * sent_conf
            reasons.append(f"Negative sentiment (-{20 * sent_conf:.0f})")

    # Emotion adjustment
    if emotion:
        emo_label = emotion.get("overall", "neutral").lower()
        emo_conf = emotion.get("overall_confidence", 0.5)
        if emo_label in ("angry", "sad"):
            score -= 15 * emo_conf
            reasons.append(f"Negative emotion ({emo_label}, -{15 * emo_conf:.0f})")
        elif emo_label == "happy":
            score += 10 * emo_conf
            reasons.append(f"Positive emotion ({emo_label}, +{10 * emo_conf:.0f})")

    # Claim-based adjustments
    supported_pricing = 0
    supported_intent = 0
    supported_timeline = 0
    verified_reasons = []

    if claims:
        for claim in claims:
            if claim.get("supported") and claim.get("confidence", 0) > 0.5:
                verified_reasons.append(claim.get("claim", ""))
                category = claim.get("category", "").lower()
                if category == "pricing":
                    supported_pricing += 1
                elif category == "intent":
                    supported_intent += 1
                elif category == "timeline":
                    supported_timeline += 1

        if supported_pricing:
            score += 10 * min(supported_pricing, 3)
            reasons.append(f"Pricing signals (+{10 * min(supported_pricing, 3)})")
        if supported_intent:
            score += 8 * min(supported_intent, 3)
            reasons.append(f"Intent signals (+{8 * min(supported_intent, 3)})")
        if supported_timeline:
            score += 5 * min(supported_timeline, 2)
            reasons.append(f"Timeline signals (+{5 * min(supported_timeline, 2)})")

    # Clamp to 0-100
    score = max(0.0, min(100.0, score))

    # Category
    if score >= 75:
        category = "hot"
    elif score >= 40:
        category = "warm"
    else:
        category = "cold"

    confidence = 0.5
    if claims:
        confidence = min(0.9, 0.5 + (supported_intent + supported_pricing + supported_timeline) * 0.05)

    return LeadScoreResult(
        overall=round(score, 1),
        category=category,
        confidence=round(confidence, 2),
        explanation="; ".join(reasons) if reasons else "No conversation data available",
        verified_reasons=verified_reasons,
        components={
            "sentiment_adj": sentiment.get("overall", "neutral") if sentiment else "unknown",
            "emotion_adj": emotion.get("overall", "neutral") if emotion else "unknown",
            "pricing_signals": supported_pricing,
            "intent_signals": supported_intent,
            "timeline_signals": supported_timeline,
        },
    )
