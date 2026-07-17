import asyncio
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np

try:
    from xgboost import XGBClassifier
except ImportError:
    XGBClassifier = None

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    import shap
except ImportError:
    shap = None

from app.config.settings import get_settings
from app.analysis.services.learned_bant_service import LearnedBANTService
from app.analysis.services.memory_service import memory_service

_settings = get_settings()

_LEAD_CONVERSION_MODEL_PATH: str = getattr(
    _settings, "lead_conversion_model_path", "AI_MODELS/lead_conversion/model.joblib"
)
_BANT_MODEL_PATH: str = _settings.BANT_MODEL_PATH

logger = logging.getLogger(__name__)


class LeadIntelligenceService:
    model = None
    feature_names: List[str] = []
    customer_profiles: Dict[str, Dict[str, Any]] = {}
    lead_history: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def _ensure_model(cls):
        if cls.model is not None:
            return cls.model

        model_path = Path(_LEAD_CONVERSION_MODEL_PATH)
        if not model_path.is_file():
            raise RuntimeError(
                "Lead conversion model is not trained. Run "
                "`python -m training.train_lead_conversion --dataset <real-data.csv-or-jsonl>` first."
            )
        artifact = joblib.load(model_path)
        if not isinstance(artifact, dict) or "model" not in artifact or "feature_names" not in artifact:
            raise ValueError(f"Invalid lead conversion model artifact: {model_path}")
        expected_features = cls._build_feature_names()
        if artifact["feature_names"] != expected_features:
            raise ValueError("Lead conversion model feature schema does not match the running application")
        cls.model = artifact["model"]
        cls.feature_names = artifact["feature_names"]
        logger.info("Loaded lead conversion model from %s", model_path)
        return cls.model

    @classmethod
    def train_conversion_model(
        cls,
        records: List[Dict[str, Any]],
        model_path: Optional[str] = None,
        minimum_records: int = 50,
    ) -> Dict[str, Any]:
        if len(records) < minimum_records:
            raise ValueError(f"At least {minimum_records} real labeled records are required")

        feature_names = cls._build_feature_names()
        rows: List[List[float]] = []
        labels: List[int] = []
        for index, record in enumerate(records, start=1):
            text = record.get("text")
            label = record.get("converted")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Record {index} requires non-empty text")
            if label not in (0, 1, False, True):
                raise ValueError(f"Record {index} converted must be 0 or 1")
            features = cls._build_engineered_features(
                text,
                voice_emotion=record.get("voice_emotion"),
                emotion_confidence=record.get("emotion_confidence"),
                history=record.get("history"),
                metadata=record.get("metadata"),
                crm_context=record.get("crm_context"),
                business_docs=record.get("business_docs"),
            )
            rows.append([features[name] for name in feature_names])
            labels.append(int(label))

        class_counts = Counter(labels)
        if set(class_counts) != {0, 1} or min(class_counts.values()) < 10:
            raise ValueError("Dataset requires both outcomes with at least 10 records per class")

        X = np.array(rows, dtype=float)
        y = np.array(labels, dtype=int)
        if XGBClassifier is not None:
            model = XGBClassifier(
                n_estimators=120,
                max_depth=3,
                learning_rate=0.18,
                random_state=42,
                objective="binary:logistic",
                eval_metric="logloss",
            )
        else:
            model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                GradientBoostingClassifier(random_state=42),
            )

        model.fit(X, y)
        destination = Path(model_path or _LEAD_CONVERSION_MODEL_PATH)
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "feature_names": feature_names}, destination)
        cls.model = model
        cls.feature_names = feature_names
        logger.info("Trained lead conversion model from %d real records", len(records))
        return {
            "model_path": str(destination),
            "records": len(records),
            "converted": class_counts[1],
            "not_converted": class_counts[0],
            "model_type": type(model).__name__,
        }

    @classmethod
    def calculate_lead_scores(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_text = cls._normalize_text(text or "")
        history_text = " ".join(
            item.get("content", item.get("text", ""))
            for item in (history or [])
            if isinstance(item, dict) and (item.get("content") or item.get("text"))
        )
        combined_text = f"{normalized_text} {history_text}".strip()
        tokens = re.findall(r"[a-zA-Z0-9_]+", combined_text.lower())
        token_counts = Counter(tokens)

        icp_score = cls._score_icp(combined_text, metadata or {}, crm_context or {})
        intent_score = cls._score_intent(combined_text, token_counts)
        engagement_score = cls._score_engagement(combined_text, token_counts, history or [])
        qualification_score = cls._score_qualification(combined_text, metadata or {}, crm_context or {})
        buying_signal_score = cls._score_buying_signal(combined_text)
        relationship_score = cls._score_relationship(
            combined_text,
            voice_emotion,
            emotion_confidence,
            history or [],
            metadata or {},
        )

        weighted_score = (
            0.2 * icp_score
            + 0.2 * intent_score
            + 0.2 * qualification_score
            + 0.15 * buying_signal_score
            + 0.15 * engagement_score
            + 0.1 * relationship_score
        )
        bant_scores = cls._score_bant_components(
            combined_text,
            metadata or {},
            crm_context or {},
            history=history or [],
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            signal_scores={
                "intent_score": intent_score,
                "qualification_score": qualification_score,
                "engagement_score": engagement_score,
                "buying_signal_score": buying_signal_score,
                "relationship_score": relationship_score,
            },
        )
        bant_average = sum(bant_scores.values()) / 4.0
        metric_score = round(min(100.0, max(0.0, weighted_score * 100.0)), 2)
        bant_score = round(min(100.0, max(0.0, bant_average * 100.0)), 2)
        bant_category = cls.categorize_score(bant_score)
        lead_basis = (metric_score * 0.6) + (bant_score * 0.4)
        lead_score = cls._calibrated_lead_score(
            lead_basis,
            history=history or [],
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
        )
        return {
            "icp_score": round(icp_score * 100.0, 2),
            "intent_score": round(intent_score * 100.0, 2),
            "engagement_score": round(engagement_score * 100.0, 2),
            "qualification_score": round(qualification_score * 100.0, 2),
            "buying_signal_score": round(buying_signal_score * 100.0, 2),
            "relationship_score": round(relationship_score * 100.0, 2),
            "bant_scores": {name: round(value * 100.0, 2) for name, value in bant_scores.items()},
            "bant_score": bant_score,
            "bant_category": bant_category,
            "metric_score": metric_score,
            "lead_score": round(lead_score, 2),
        }

    @classmethod
    def predict_conversion(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cls._ensure_model()
        features = cls._build_engineered_features(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )
        vector = np.array([features[name] for name in cls.feature_names], dtype=float)
        vector = cls._handle_missing_and_normalize(vector)
        probability = float(cls.model.predict_proba([vector])[0][1])
        return {
            "conversion_probability": round(probability, 4),
            "conversion_probability_percent": round(probability * 100.0, 2),
            "feature_importance": cls._feature_importance(),
            "engineered_features": features,
            "shap_available": shap is not None,
        }

    @classmethod
    def categorize_lead(cls, lead_score: float) -> str:
        if lead_score >= 75:
            return "Hot Lead"
        if lead_score >= 40:
            return "Warm Lead"
        return "Cold Lead"

    @staticmethod
    def categorize_score(score: float) -> str:
        if score >= 75:
            return "hot"
        if score >= 40:
            return "warm"
        return "cold"

    @classmethod
    def generate_next_action(
        cls,
        lead_score: float,
        scores: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
    ) -> str:
        if lead_score >= 75:
            return "Send a tailored proposal and confirm implementation timeline."
        if lead_score >= 40:
            return "Provide a value summary and ask for a follow-up meeting."
        if scores and float(scores.get("bant_score", 0.0)) >= 40:
            return "Re-qualify the need and offer a short discovery call."
        return "Continue nurturing the lead with helpful content and periodic follow-up."

    @classmethod
    def update_customer_profile(
        cls,
        session_id: str,
        profile: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        merged = dict(cls.customer_profiles.get(session_id, {}))
        if profile:
            merged.update(profile)
        if metadata:
            merged.update(metadata)
        merged.setdefault("returning_customer", bool(merged.get("returning_customer", False)))
        merged.setdefault("customer_lifetime", 0)
        cls.customer_profiles[session_id] = merged
        return merged

    @classmethod
    def store_lead_history(
        cls,
        session_id: str,
        payload: Dict[str, Any],
        text: Optional[str] = None,
    ) -> Dict[str, Any]:
        history = list(cls.lead_history.get(session_id, []))
        record = {
            **payload,
            "timestamp": payload.get("timestamp") or "now",
            "role": payload.get("role", "user"),
            "content": text or payload.get("content", payload.get("text", "")),
        }
        history.append(record)
        cls.lead_history[session_id] = history[-20:]
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, memory_service.append_user_message, session_id, text or payload.get("text", ""))
        except Exception as exc:
            logger.debug("Lead history persistence skipped: %s", exc)
        return record

    @classmethod
    def score(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        scores = cls.calculate_lead_scores(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )
        lead_score = scores["lead_score"]
        engineered_features = cls._build_engineered_features(
            text,
            voice_emotion=voice_emotion,
            emotion_confidence=emotion_confidence,
            history=history,
            metadata=metadata,
            crm_context=crm_context,
            business_docs=business_docs,
        )
        prediction = cls._conversion_prediction(engineered_features, lead_score)
        lead_category = cls.categorize_lead(lead_score)
        bant_category = scores.get("bant_category", cls.categorize_score(scores.get("bant_score", 0.0)))
        recommendation = cls.generate_next_action(lead_score, scores=scores, text=text)
        conversion_category = "hot" if lead_score >= 75 else "warm" if lead_score >= 40 else "cold"

        return {
            "text": text,
            "scores": {
                "icp_score": scores["icp_score"],
                "intent_score": scores["intent_score"],
                "engagement_score": scores["engagement_score"],
                "qualification_score": scores["qualification_score"],
                "buying_signal_score": scores["buying_signal_score"],
                "relationship_score": scores["relationship_score"],
            },
            "icp_score": scores["icp_score"],
            "intent_score": scores["intent_score"],
            "engagement_score": scores["engagement_score"],
            "qualification_score": scores["qualification_score"],
            "buying_signal_score": scores["buying_signal_score"],
            "relationship_score": scores["relationship_score"],
            "conversion_probability": prediction["conversion_probability"],
            "conversion_probability_percent": prediction["conversion_probability_percent"],
            "xgboost_probability": prediction["conversion_probability"],
            "xgboost_probability_percent": prediction["conversion_probability_percent"],
            "conversion_category": conversion_category,
            "bant_scores": scores.get("bant_scores"),
            "bant_score": scores.get("bant_score"),
            "bant_category": bant_category,
            "metric_score": scores.get("metric_score"),
            "lead_score": lead_score,
            "lead_category": lead_category,
            "recommendation": recommendation,
            "engineered_features": engineered_features,
            "feature_importance": prediction["feature_importance"],
            "model": prediction["model"],
            "probabilities": {
                "cold": round(max(0.0, 1.0 - prediction["conversion_probability"]), 4),
                "warm": round(min(0.99, max(0.0, abs(prediction["conversion_probability"] - 0.5))), 4),
                "hot": round(prediction["conversion_probability"], 4),
            },
            "shap_available": prediction["shap_available"],
        }

    @classmethod
    def _build_feature_names(cls) -> List[str]:
        return [
            "sentiment_score",
            "emotion_strength",
            "question_count",
            "question_density",
            "conversation_length",
            "response_frequency",
            "avg_reply_time",
            "voice_energy",
            "speech_rate",
            "numeric_evidence",
            "amount_evidence",
            "date_evidence",
            "avg_turn_words",
            "user_turn_ratio",
            "metadata_completeness",
            "crm_context_completeness",
            "continuity_score",
            "industry_match",
            "company_size_score",
            "annual_revenue_score",
            "tech_stack_match",
            "decision_maker_score",
            "country_match",
            "business_requirement_match",
            "current_software_match",
            "need_match",
            "ideal_customer_similarity",
            "returning_customer",
            "customer_lifetime",
            "budget_signal",
            "timeline_signal",
            "authority_signal",
            "need_signal",
            "decision_confidence",
            "sentiment_trend_score",
            "business_docs_count",
        ]

    @classmethod
    def _build_engineered_features(
        cls,
        text: str,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        crm_context: Optional[Dict[str, Any]] = None,
        business_docs: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        normalized_text = cls._normalize_text(text or "")
        history_text = " ".join(
            item.get("content", item.get("text", ""))
            for item in (history or [])
            if isinstance(item, dict) and (item.get("content") or item.get("text"))
        )
        combined_text = f"{normalized_text} {history_text}".strip()
        tokens = re.findall(r"[a-zA-Z0-9_]+", combined_text.lower())
        text_metrics = cls._text_measurements(combined_text)
        live_signals = cls._conversation_signal_profile(history or [], voice_emotion, emotion_confidence)

        features: Dict[str, float] = {}
        sentiment_score = cls._sentiment_score(combined_text)
        features["sentiment_score"] = sentiment_score
        features["emotion_strength"] = cls._emotion_strength(voice_emotion, emotion_confidence)
        features["question_count"] = text_metrics["question_count"]
        features["question_density"] = live_signals["question_density"]
        features["conversation_length"] = min(1.0, len(tokens) / 80.0)
        features["response_frequency"] = min(1.0, len(history or []) / 10.0)
        features["avg_reply_time"] = min(1.0, 0.25 + (len(history or []) * 0.04))
        features["voice_energy"] = cls._emotion_strength(voice_emotion, emotion_confidence)
        features["speech_rate"] = min(1.0, len(tokens) / 120.0)
        features["numeric_evidence"] = text_metrics["numeric_evidence"]
        features["amount_evidence"] = cls._budget_signal(combined_text)
        features["date_evidence"] = cls._timeline_signal(combined_text)
        features["avg_turn_words"] = live_signals["reply_density"]
        features["user_turn_ratio"] = live_signals["user_turn_ratio"]
        features["metadata_completeness"] = cls._mapping_completeness(metadata or {})
        features["crm_context_completeness"] = cls._mapping_completeness(crm_context or {})
        features["continuity_score"] = 1.0 if len(history or []) >= 2 else 0.0

        metadata = metadata or {}
        crm_context = crm_context or {}
        business_docs = business_docs or []
        features["industry_match"] = float(metadata.get("industry_match", 0.5 if crm_context else 0.4))
        features["company_size_score"] = float(metadata.get("company_size_score", 0.5))
        features["annual_revenue_score"] = float(metadata.get("annual_revenue_score", 0.5))
        features["tech_stack_match"] = float(metadata.get("tech_stack_match", 0.5))
        features["decision_maker_score"] = float(metadata.get("decision_maker_score", 0.5))
        features["country_match"] = float(metadata.get("country_match", 0.5))
        features["business_requirement_match"] = float(metadata.get("business_requirement_match", 0.5))
        features["current_software_match"] = float(metadata.get("current_software_match", 0.5))
        features["need_match"] = float(metadata.get("need_match", 0.5))
        features["ideal_customer_similarity"] = float(metadata.get("ideal_customer_similarity", 0.5))
        features["returning_customer"] = 1.0 if bool(metadata.get("returning_customer", False)) or bool(crm_context.get("returning_customer", False)) else 0.0
        features["customer_lifetime"] = min(1.0, float(metadata.get("customer_lifetime", crm_context.get("customer_lifetime", 0))) / 10.0)
        budget_signal = cls._budget_signal(combined_text)
        timeline_signal = cls._timeline_signal(combined_text)
        authority_signal = float(metadata.get("decision_maker_score", crm_context.get("decision_maker_score", 0.5)))
        need_signal = float(metadata.get("need_match", crm_context.get("need_match", 0.5)))
        features["budget_signal"] = budget_signal
        features["timeline_signal"] = timeline_signal
        features["authority_signal"] = min(1.0, max(0.0, authority_signal))
        features["need_signal"] = min(1.0, max(0.0, need_signal))
        features["decision_confidence"] = round(min(1.0, 0.35 + (authority_signal * 0.65)), 4)
        features["sentiment_trend_score"] = sentiment_score
        features["business_docs_count"] = min(1.0, len(business_docs) / 5.0)
        return features

    @classmethod
    def _handle_missing_and_normalize(cls, vector: np.ndarray) -> np.ndarray:
        filled = np.nan_to_num(vector.astype(float), nan=0.0, posinf=1.0, neginf=0.0)
        return np.clip(filled, 0.0, 1.0)

    @classmethod
    def _feature_importance(cls) -> Dict[str, float]:
        model = cls._ensure_model()
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        else:
            importances = np.zeros(len(cls.feature_names), dtype=float)
        ranked = sorted(
            zip(cls.feature_names, importances.tolist()),
            key=lambda item: item[1],
            reverse=True,
        )
        return {name: round(float(score), 4) for name, score in ranked[:10]}

    @classmethod
    def _conversion_prediction(
        cls,
        features: Dict[str, float],
        lead_score: float,
    ) -> Dict[str, Any]:
        if cls.model is None and not Path(_LEAD_CONVERSION_MODEL_PATH).is_file():
            return cls._fast_conversion_prediction(lead_score)

        model = cls._ensure_model()
        vector = np.array([features[name] for name in cls.feature_names], dtype=float)
        vector = cls._handle_missing_and_normalize(vector)
        probability = float(model.predict_proba([vector])[0][1])
        return {
            "conversion_probability": round(probability, 4),
            "conversion_probability_percent": round(probability * 100.0, 2),
            "feature_importance": cls._feature_importance(),
            "shap_available": shap is not None,
            "model": type(model).__name__,
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        replacements = {
            "rising": "pricing",
            "priceing": "pricing",
            "prizing": "pricing",
            "life demo": "live demo",
            "lime demo": "live demo",
            "leave demo": "live demo",
            "implement timeline": "implementation timeline",
        }
        for source, target in replacements.items():
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized)
        return normalized

    @classmethod
    def _calibrated_lead_score(
        cls,
        weighted_score: float,
        history: Optional[List[Dict[str, Any]]] = None,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
    ) -> float:
        signals = cls._conversation_signal_profile(history or [], voice_emotion, emotion_confidence)
        momentum = (
            signals["turn_depth"] * 0.35
            + signals["question_density"] * 0.25
            + signals["reply_density"] * 0.2
            + signals["voice_confidence"] * 0.2
        )
        adjusted_score = weighted_score + (momentum * 6.0)
        return round(min(100.0, max(0.0, adjusted_score)), 2)

    @staticmethod
    def _budget_signal(text: str) -> float:
        amount_patterns = [
            r"(?<!\w)[₹$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?[kmb])?(?!\w)",
            r"(?<!\w)\d[\d,]*(?:\.\d+)?\s?(?:k|m|bn|b)(?!\w)",
            r"\b\d[\d,]*(?:\.\d{1,2})?\b",
        ]
        matches = 0
        for pattern in amount_patterns:
            matches += len(re.findall(pattern, text, flags=re.IGNORECASE))
        if not matches:
            return 0.0
        return round(min(1.0, 0.35 + (matches * 0.18)), 4)

    @staticmethod
    def _timeline_signal(text: str) -> float:
        time_patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
            r"\bq[1-4]\b",
            r"\bfy\d{2,4}\b",
            r"\b\d+\s*(?:d|w|m|q|y)\b",
        ]
        matches = 0
        for pattern in time_patterns:
            matches += len(re.findall(pattern, text, flags=re.IGNORECASE))
        if not matches:
            return 0.0
        return round(min(1.0, 0.3 + (matches * 0.2)), 4)

    @staticmethod
    def _authority_signal(metadata: Dict[str, Any], crm_context: Dict[str, Any]) -> float:
        score = 0.0
        for source in (metadata, crm_context):
            raw_score = source.get("decision_maker_score")
            if raw_score is not None:
                score = max(score, float(raw_score))
        return round(min(1.0, max(0.0, score)), 4)

    @classmethod
    def _need_signal(
        cls,
        metadata: Dict[str, Any],
        crm_context: Dict[str, Any],
        signal_scores: Optional[Dict[str, float]] = None,
    ) -> float:
        signal_scores = signal_scores or {}
        score = 0.0
        for source in (metadata, crm_context):
            raw_score = source.get("need_match")
            if raw_score is not None:
                score = max(score, float(raw_score))
            raw_score = source.get("business_requirement_match")
            if raw_score is not None:
                score = max(score, float(raw_score))
        score = max(score, float(signal_scores.get("qualification_score", 0.0)) * 0.8)
        score = max(score, float(signal_scores.get("engagement_score", 0.0)) * 0.5)
        return round(min(1.0, max(0.0, score)), 4)

    @classmethod
    def _score_bant_components(
        cls,
        text: str,
        metadata: Dict[str, Any],
        crm_context: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        voice_emotion: Optional[str] = None,
        emotion_confidence: Optional[float] = None,
        signal_scores: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        learned_scores = LearnedBANTService.predict_sync(text)
        if learned_scores is not None:
            return learned_scores
        signal_scores = signal_scores or {}
        live_signals = cls._conversation_signal_profile(history or [], voice_emotion, emotion_confidence)
        budget_score = cls._budget_signal(text)
        timeline_score = cls._timeline_signal(text)
        authority_score = cls._authority_signal(metadata, crm_context)
        need_score = cls._need_signal(metadata, crm_context, signal_scores)

        budget_score = min(
            1.0,
            round(
                budget_score
                + live_signals["turn_depth"] * 0.08
                + live_signals["reply_density"] * 0.05,
                4,
            ),
        )
        budget_override = metadata.get("budget")
        if budget_override is None:
            budget_override = crm_context.get("budget")
        if budget_override is not None:
            budget_score = max(budget_score, cls._coerce_unit_score(budget_override))

        timeline_score = min(
            1.0,
            round(
                timeline_score
                + live_signals["turn_depth"] * 0.05
                + live_signals["question_density"] * 0.08,
                4,
            ),
        )

        authority_override = metadata.get("decision_maker_score")
        if authority_override is None:
            authority_override = crm_context.get("decision_maker_score")
        if authority_override is not None:
            authority_score = max(authority_score, cls._coerce_unit_score(authority_override))
        authority_score = min(
            1.0,
            round(
                authority_score
                + live_signals["reply_density"] * 0.08
                + live_signals["voice_confidence"] * 0.06,
                4,
            ),
        )

        need_score = min(
            1.0,
            round(
                max(need_score, float(signal_scores.get("qualification_score", 0.0)) * 0.6)
                + live_signals["question_density"] * 0.12
                + live_signals["turn_depth"] * 0.08,
                4,
            ),
        )

        return {
            "budget": round(min(1.0, budget_score), 4),
            "authority": round(min(1.0, authority_score), 4),
            "need": round(min(1.0, need_score), 4),
            "timeline": round(min(1.0, timeline_score), 4),
        }

    @staticmethod
    def _coerce_unit_score(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        if numeric > 1.0:
            numeric = numeric / 100.0
        return min(1.0, max(0.0, numeric))

    @staticmethod
    def _conversation_signal_profile(
        history: List[Dict[str, Any]],
        voice_emotion: Optional[str],
        emotion_confidence: Optional[float],
    ) -> Dict[str, float]:
        contents = [
            str(item.get("content", item.get("text", ""))).strip()
            for item in history
            if isinstance(item, dict) and (item.get("content") or item.get("text"))
        ]
        user_contents = [
            str(item.get("content", item.get("text", ""))).strip()
            for item in history
            if isinstance(item, dict)
            and (item.get("content") or item.get("text"))
            and str(item.get("role", "")).lower() in {"user", "customer", "lead", ""}
        ]
        total_words = sum(len(content.split()) for content in contents)
        question_count = sum(content.count("?") for content in contents)
        turn_depth = min(1.0, len(contents) / 8.0)
        reply_density = min(1.0, total_words / max(40.0, len(contents) * 16.0))
        question_density = min(1.0, question_count / max(1.0, len(contents) / 2.0))
        user_participation = min(1.0, len(user_contents) / max(1.0, len(contents)))
        voice_confidence = 0.0
        if voice_emotion in {"happy", "excited", "calm", "friendly"} and emotion_confidence is not None:
            voice_confidence = min(1.0, max(0.0, float(emotion_confidence)))
        return {
            "turn_depth": round(turn_depth, 4),
            "reply_density": round(reply_density * user_participation, 4),
            "question_density": round(question_density, 4),
            "user_turn_ratio": round(user_participation, 4),
            "voice_confidence": round(voice_confidence, 4),
        }

    @staticmethod
    def _text_measurements(text: str) -> Dict[str, float]:
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        token_count = max(1, len(tokens))
        question_count = text.count("?")
        numeric_matches = re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", text)
        uppercase_tokens = re.findall(r"\b[A-Z]{2,}\b", text)
        punctuation_count = sum(text.count(mark) for mark in ("?", "!", "."))
        return {
            "question_count": min(1.0, question_count / 4.0),
            "numeric_evidence": min(1.0, len(numeric_matches) / 4.0),
            "uppercase_ratio": min(1.0, len(uppercase_tokens) / token_count),
            "punctuation_density": min(1.0, punctuation_count / token_count),
            "token_count": min(1.0, token_count / 120.0),
        }

    @staticmethod
    def _mapping_completeness(values: Dict[str, Any]) -> float:
        if not values:
            return 0.0
        useful_values = sum(1 for value in values.values() if value not in (None, "", [], {}))
        return round(min(1.0, useful_values / 8.0), 4)

    @staticmethod
    def _fast_conversion_prediction(lead_score: float) -> Dict[str, Any]:
        probability = min(0.98, max(0.03, lead_score / 100.0))
        return {
            "conversion_probability": round(probability, 4),
            "conversion_probability_percent": round(probability * 100.0, 2),
            "engineered_features": {"lead_score": round(lead_score / 100.0, 4)},
            "feature_importance": {
                "buying_signal_score": 0.35,
                "intent_score": 0.25,
                "qualification_score": 0.2,
                "icp_score": 0.1,
                "engagement_score": 0.06,
                "relationship_score": 0.04,
            },
            "shap_available": False,
            "model": "realtime_signal_scoring",
        }

    @classmethod
    def _score_icp(cls, text: str, metadata: Dict[str, Any], crm_context: Dict[str, Any]) -> float:
        metadata = metadata or {}
        crm_context = crm_context or {}
        score = 0.15 + cls._text_measurements(text)["token_count"] * 0.1
        for field, weight in [
            ("industry_match", 0.2),
            ("company_size_score", 0.15),
            ("annual_revenue_score", 0.12),
            ("tech_stack_match", 0.12),
            ("ideal_customer_similarity", 0.16),
        ]:
            value = metadata.get(field, crm_context.get(field))
            if value is not None:
                score += cls._coerce_unit_score(value) * weight
        return min(1.0, round(score, 4))

    @staticmethod
    def _score_intent(text: str, token_counts: Counter) -> float:
        measurements = LeadIntelligenceService._text_measurements(text)
        lexical_variety = min(1.0, len(token_counts) / max(1.0, sum(token_counts.values())))
        score = (
            0.2
            + measurements["question_count"] * 0.2
            + measurements["numeric_evidence"] * 0.25
            + measurements["token_count"] * 0.2
            + lexical_variety * 0.15
        )
        return min(1.0, round(score, 4))

    @classmethod
    def _score_engagement(cls, text: str, token_counts: Counter, history: List[Dict[str, Any]]) -> float:
        if not text:
            return 0.0
        base = min(1.0, len(text.split()) / 45.0)
        if "?" in text:
            base += 0.1
        if len(history) >= 2:
            base += 0.08
        base += min(0.12, cls._text_measurements(text)["question_count"] * 0.12)
        return min(1.0, round(base, 4))

    @staticmethod
    def _score_qualification(text: str, metadata: Dict[str, Any], crm_context: Dict[str, Any]) -> float:
        score = 0.1
        score += LeadIntelligenceService._budget_signal(text) * 0.22
        score += LeadIntelligenceService._timeline_signal(text) * 0.22
        score += LeadIntelligenceService._authority_signal(metadata, crm_context) * 0.22
        score += LeadIntelligenceService._need_signal(metadata, crm_context) * 0.24
        if metadata.get("budget") or crm_context.get("budget"):
            score += 0.1
        return min(1.0, round(score, 4))

    @staticmethod
    def _score_buying_signal(text: str) -> float:
        measurements = LeadIntelligenceService._text_measurements(text)
        score = (
            0.15
            + LeadIntelligenceService._budget_signal(text) * 0.35
            + LeadIntelligenceService._timeline_signal(text) * 0.3
            + measurements["question_count"] * 0.1
            + measurements["token_count"] * 0.1
        )
        return min(1.0, round(score, 4))

    @classmethod
    def _score_relationship(
        cls,
        text: str,
        voice_emotion: Optional[str],
        emotion_confidence: Optional[float],
        history: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> float:
        score = 0.25
        score += cls._text_measurements(text)["punctuation_density"] * 0.05
        if bool(metadata.get("returning_customer", False)):
            score += 0.2
        if len(history) >= 2:
            score += 0.15
        if voice_emotion in {"happy", "calm", "friendly"}:
            score += 0.15
        if emotion_confidence is not None:
            score += min(0.15, float(emotion_confidence) * 0.15)
        return min(1.0, round(score, 4))

    @staticmethod
    def _sentiment_score(text: str) -> float:
        measurements = LeadIntelligenceService._text_measurements(text)
        score = 0.5
        score += measurements["punctuation_density"] * 0.08
        score -= measurements["uppercase_ratio"] * 0.08
        return round(min(1.0, max(0.0, score)), 4)

    @staticmethod
    def _emotion_strength(voice_emotion: Optional[str], emotion_confidence: Optional[float]) -> float:
        if voice_emotion in {"happy", "excited", "calm"}:
            return 0.8 if emotion_confidence is None else min(1.0, 0.6 + float(emotion_confidence) * 0.2)
        if voice_emotion in {"angry", "frustrated", "sad"}:
            return 0.4 if emotion_confidence is None else min(1.0, 0.3 + float(emotion_confidence) * 0.2)
        return 0.5 if emotion_confidence is None else min(1.0, 0.4 + float(emotion_confidence) * 0.15)



