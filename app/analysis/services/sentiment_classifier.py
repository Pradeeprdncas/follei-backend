import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


TOKEN_PATTERN = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)
NEGATIONS = {"no", "not", "never", "neither", "nor", "cannot", "can't", "dont", "don't"}


def tokenize(text: str) -> List[str]:
    tokens = TOKEN_PATTERN.findall(text.lower())
    result: List[str] = []
    negate_for = 0
    for token in tokens:
        if token in NEGATIONS:
            result.append(token)
            negate_for = 3
            continue
        result.append(f"not_{token}" if negate_for else token)
        negate_for = max(0, negate_for - 1)
    return result


class MultinomialNaiveBayes:
    def __init__(self, alpha: float = 1.0):
        if alpha <= 0:
            raise ValueError("alpha must be greater than zero")
        self.alpha = alpha
        self.labels: List[str] = []
        self.vocabulary: List[str] = []
        self.class_log_prior: Dict[str, float] = {}
        self.feature_log_prob: Dict[str, Dict[str, float]] = {}
        self.unknown_log_prob: Dict[str, float] = {}

    @property
    def is_fitted(self) -> bool:
        return bool(self.labels and self.vocabulary and self.feature_log_prob)

    def fit(self, texts: Sequence[str], labels: Sequence[str]) -> "MultinomialNaiveBayes":
        if len(texts) != len(labels) or not texts:
            raise ValueError("texts and labels must be non-empty and have the same length")

        class_document_counts = Counter(labels)
        if len(class_document_counts) < 2:
            raise ValueError("training data must contain at least two sentiment labels")

        token_counts: Dict[str, Counter] = defaultdict(Counter)
        vocabulary = set()
        for text, label in zip(texts, labels):
            if not isinstance(text, str) or not text.strip():
                raise ValueError("every training text must be a non-empty string")
            tokens = tokenize(text)
            token_counts[label].update(tokens)
            vocabulary.update(tokens)

        self.labels = sorted(class_document_counts)
        self.vocabulary = sorted(vocabulary)
        total_documents = len(texts)
        vocabulary_size = len(self.vocabulary)

        for label in self.labels:
            self.class_log_prior[label] = math.log(
                class_document_counts[label] / total_documents
            )
            total_tokens = sum(token_counts[label].values())
            denominator = total_tokens + self.alpha * vocabulary_size
            self.unknown_log_prob[label] = math.log(self.alpha / denominator)
            self.feature_log_prob[label] = {
                token: math.log(
                    (token_counts[label].get(token, 0) + self.alpha) / denominator
                )
                for token in self.vocabulary
            }
        return self

    def predict_proba(self, text: str) -> Dict[str, float]:
        if not self.is_fitted:
            raise RuntimeError("classifier has not been trained")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")

        counts = Counter(tokenize(text))
        scores = {}
        for label in self.labels:
            score = self.class_log_prior[label]
            probabilities = self.feature_log_prob[label]
            unknown_probability = self.unknown_log_prob[label]
            score += sum(
                count * probabilities.get(token, unknown_probability)
                for token, count in counts.items()
            )
            scores[label] = score

        max_score = max(scores.values())
        exponentials = {
            label: math.exp(score - max_score) for label, score in scores.items()
        }
        total = sum(exponentials.values())
        return {label: value / total for label, value in exponentials.items()}

    def predict(self, text: str) -> Tuple[str, float, Dict[str, float]]:
        probabilities = self.predict_proba(text)
        known_tokens = set(tokenize(text)).intersection(self.vocabulary)
        if not known_tokens and "neutral" in probabilities:
            label = "neutral"
        else:
            label = max(probabilities, key=probabilities.get)
        return label, probabilities[label], probabilities

    def save(self, path: str) -> None:
        if not self.is_fitted:
            raise RuntimeError("classifier has not been trained")
        model_path = Path(path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "multinomial_naive_bayes",
            "version": 1,
            "alpha": self.alpha,
            "labels": self.labels,
            "vocabulary": self.vocabulary,
            "class_log_prior": self.class_log_prior,
            "feature_log_prob": self.feature_log_prob,
            "unknown_log_prob": self.unknown_log_prob,
        }
        model_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "MultinomialNaiveBayes":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model_type") != "multinomial_naive_bayes":
            raise ValueError("unsupported sentiment model format")
        model = cls(alpha=float(payload["alpha"]))
        model.labels = list(payload["labels"])
        model.vocabulary = list(payload["vocabulary"])
        model.class_log_prior = {
            label: float(value)
            for label, value in payload["class_log_prior"].items()
        }
        model.feature_log_prob = {
            label: {token: float(value) for token, value in probabilities.items()}
            for label, probabilities in payload["feature_log_prob"].items()
        }
        model.unknown_log_prob = {
            label: float(value)
            for label, value in payload["unknown_log_prob"].items()
        }
        return model


def load_sentiment_dataset(path: str) -> Tuple[List[str], List[str]]:
    records: Iterable[dict] = json.loads(Path(path).read_text(encoding="utf-8"))
    texts: List[str] = []
    labels: List[str] = []
    for index, record in enumerate(records):
        text = record.get("text")
        label = record.get("label")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"record {index} has an invalid text value")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"record {index} has an invalid label value")
        texts.append(text)
        labels.append(label.strip().lower())
    return texts, labels
