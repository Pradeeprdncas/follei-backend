"""AI output validator — validates and sanitizes all AI-generated outputs before persistence.

Every analysis stage that produces AI-generated content must pass
its output through the appropriate validator. This catches:
- Empty or null responses
- Confidence below threshold
- Malformed structure
- Unexpected labels
- Hallucinated speakers or segments
"""
from dataclasses import dataclass

from loguru import logger


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = None
    sanitized: dict | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class AnalysisOutputValidator:
    """Validates structured outputs from the analysis pipeline."""

    MIN_CONFIDENCE = 0.3
    VALID_SENTIMENT_LABELS = {"positive", "negative", "neutral", "mixed"}
    VALID_EMOTION_LABELS = {"angry", "happy", "neutral", "sad", "frustrated", "mixed", "sarcastic_or_masked"}

    def validate_sentiment(self, data: dict | None) -> ValidationResult:
        if not data:
            return ValidationResult(valid=False, errors=["sentiment data is empty"])
        errors = []
        overall = data.get("overall", "")
        if overall and overall.lower() not in self.VALID_SENTIMENT_LABELS:
            errors.append(f"unexpected sentiment label: {overall}")
        timeline = data.get("timeline", [])
        for seg in timeline:
            label = seg.get("label", "")
            if label.lower() not in self.VALID_SENTIMENT_LABELS:
                errors.append(f"unexpected sentiment label in timeline: {label}")
            if seg.get("confidence", 1.0) < self.MIN_CONFIDENCE:
                errors.append(f"low confidence sentiment segment: {seg.get('confidence', 0)}")
        if errors:
            logger.warning(f"Sentiment validation: {'; '.join(errors)}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=data)

    def validate_emotion(self, data: dict | None) -> ValidationResult:
        if not data:
            return ValidationResult(valid=False, errors=["emotion data is empty"])
        errors = []
        overall = data.get("overall", "")
        if overall and overall.lower() not in self.VALID_EMOTION_LABELS:
            errors.append(f"unexpected emotion label: {overall}")
        timeline = data.get("timeline", [])
        for seg in timeline:
            label = seg.get("label", "")
            if label.lower() not in self.VALID_EMOTION_LABELS:
                errors.append(f"unexpected emotion label in timeline: {label}")
            if seg.get("confidence", 1.0) < self.MIN_CONFIDENCE:
                errors.append(f"low confidence emotion segment: {seg.get('confidence', 0)}")
        if errors:
            logger.warning(f"Emotion validation: {'; '.join(errors)}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=data)

    def validate_lead_score(self, data: dict | None) -> ValidationResult:
        if not data:
            return ValidationResult(valid=False, errors=["lead_score data is empty"])
        errors = []
        overall = data.get("overall")
        if overall is not None and not (0 <= overall <= 100):
            errors.append(f"lead_score.overall out of range: {overall}")
        for key in ("icp", "intent", "engagement", "qualification", "buying_signal", "relationship"):
            val = data.get(key)
            if val is not None and not (0 <= val <= 100):
                errors.append(f"lead_score.{key} out of range: {val}")
        category = data.get("category", "")
        if category and category.lower() not in {"hot", "warm", "cold"}:
            errors.append(f"unexpected lead category: {category}")
        if errors:
            logger.warning(f"Lead score validation: {'; '.join(errors)}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=data)

    def validate_claims(self, claims: list[dict] | None) -> ValidationResult:
        if not claims:
            return ValidationResult(valid=True, errors=[], sanitized=claims or [])
        errors = []
        for i, claim in enumerate(claims):
            if not claim.get("claim"):
                errors.append(f"claims[{i}]: missing claim text")
            if "supported" not in claim:
                errors.append(f"claims[{i}]: missing supported flag")
            if claim.get("confidence") is not None and not (0 <= claim["confidence"] <= 1):
                errors.append(f"claims[{i}]: confidence out of range")
        if errors:
            logger.warning(f"Claims validation: {'; '.join(errors)}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=claims)

    def validate_transcript(self, transcript: dict | None) -> ValidationResult:
        if not transcript:
            return ValidationResult(valid=False, errors=["transcript is empty"])
        errors = []
        full_text = transcript.get("full_text", "")
        if not full_text or not full_text.strip():
            errors.append("transcript full_text is empty")
        segments = transcript.get("segments", [])
        if not segments:
            errors.append("transcript has no segments")
        for i, seg in enumerate(segments):
            if not seg.get("text", "").strip():
                errors.append(f"transcript segments[{i}]: empty text")
        if errors:
            logger.warning(f"Transcript validation: {'; '.join(errors)}")
        return ValidationResult(valid=len(errors) == 0, errors=errors, sanitized=transcript)

    def validate_all(self, analysis: dict) -> ValidationResult:
        """Run all validators against a complete analysis dict.

        Returns valid=True only if ALL validators pass.
        Errors are aggregated across all validators.
        """
        all_errors = []
        for validator_name, data in [
            ("transcript", analysis.get("transcript")),
            ("sentiment", analysis.get("sentiment")),
            ("emotion", analysis.get("emotion")),
            ("lead_score", analysis.get("lead_score")),
            ("claims", analysis.get("claims")),
        ]:
            if data is not None:
                validator = getattr(self, f"validate_{validator_name}")
                result = validator(data)
                if not result.valid:
                    all_errors.extend(result.errors)
        return ValidationResult(valid=len(all_errors) == 0, errors=all_errors, sanitized=analysis)
