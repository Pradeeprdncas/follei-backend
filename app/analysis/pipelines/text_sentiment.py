from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from app.analysis.pipelines.text_preprocessing import NLPPreprocessor


@dataclass
class TextSentimentResult:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    model: str = "tfidf_multinomial_naive_bayes"


class TextSentimentPipeline:
    """TF-IDF + Multinomial Naive Bayes text sentiment pipeline."""

    def __init__(self, model_path: str | None = None):
        self.model_path = Path(model_path) if model_path else None
        self.preprocessor = NLPPreprocessor()
        self.vectorizer = None
        self.classifier = None
        self.labels: List[str] = []

    def _ensure_sklearn(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.naive_bayes import MultinomialNB
        except ImportError as exc:
            raise RuntimeError(
                "scikit-learn is required for TF-IDF Multinomial Naive Bayes. "
                "Install project requirements first."
            ) from exc
        return TfidfVectorizer, MultinomialNB

    def train(
        self,
        texts: Sequence[str],
        labels: Sequence[str],
        alpha: float = 1.0,
        fit_prior: bool = False,
    ):
        if len(texts) != len(labels) or not texts:
            raise ValueError("texts and labels must be non-empty and have the same length")
        TfidfVectorizer, MultinomialNB = self._ensure_sklearn()
        cleaned = [self.preprocessor.preprocess(text) for text in texts]
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        features = self.vectorizer.fit_transform(cleaned)
        self.classifier = MultinomialNB(alpha=alpha, fit_prior=fit_prior)
        self.classifier.fit(features, labels)
        self.labels = list(self.classifier.classes_)
        return self

    def predict(self, text: str) -> TextSentimentResult:
        if self.vectorizer is None or self.classifier is None:
            self.load()
        cleaned = self.preprocessor.preprocess(text)
        features = self.vectorizer.transform([cleaned])
        probabilities_raw = self.classifier.predict_proba(features)[0]
        probabilities = {
            label: round(float(probability), 6)
            for label, probability in zip(self.classifier.classes_, probabilities_raw)
        }
        label = max(probabilities, key=probabilities.get)
        return TextSentimentResult(
            label=label,
            confidence=probabilities[label],
            probabilities=probabilities,
        )

    def save(self, path: str | None = None):
        path_obj = Path(path) if path else self.model_path
        if path_obj is None:
            raise ValueError("model path is required")
        if self.vectorizer is None or self.classifier is None:
            raise RuntimeError("pipeline has not been trained")
        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError("joblib is required to save the text sentiment pipeline") from exc
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "vectorizer": self.vectorizer,
                "classifier": self.classifier,
                "labels": self.labels,
            },
            path_obj,
        )

    def load(self, path: str | None = None):
        path_obj = Path(path) if path else self.model_path
        if path_obj is None or not path_obj.exists():
            raise RuntimeError(f"text sentiment model not found: {path_obj}")
        try:
            import joblib
        except ImportError as exc:
            raise RuntimeError("joblib is required to load the text sentiment pipeline") from exc
        payload = joblib.load(path_obj)
        self.vectorizer = payload["vectorizer"]
        self.classifier = payload["classifier"]
        self.labels = list(payload.get("labels", self.classifier.classes_))
        return self

    @staticmethod
    def why_multinomial_nb() -> str:
        return (
            "Multinomial Naive Bayes is suitable for text sentiment because text can be "
            "represented as non-negative word or TF-IDF feature counts. It is fast, "
            "stable on small-to-medium datasets, interpretable, CPU-friendly, and returns "
            "class probabilities for positive, negative, and neutral labels."
        )


def load_hf_text_records(dataset_name: str, split: str) -> tuple[List[str], List[str]]:
    from datasets import load_dataset

    dataset = load_dataset(dataset_name, split=split)
    texts: List[str] = []
    labels: List[str] = []
    label_names = None
    if "label" in dataset.features and hasattr(dataset.features["label"], "names"):
        label_names = dataset.features["label"].names
    for record in dataset:
        text = (
            record.get("sentence")
            or record.get("text")
            or record.get("transcript")
            or record.get("normalized_text")
            or ""
        )
        label_value = record.get("label") or record.get("sentiment") or record.get("emotion")
        if isinstance(label_value, int) and label_names:
            label = label_names[label_value]
        else:
            label = str(label_value).lower()
        if text and label not in {"none", "null", ""}:
            texts.append(text)
            labels.append(label)
    return texts, labels
