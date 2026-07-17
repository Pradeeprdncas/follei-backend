from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, List


CONTRACTIONS = {
    "aren't": "are not",
    "can't": "cannot",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "isn't": "is not",
    "it's": "it is",
    "i'm": "i am",
    "i've": "i have",
    "shouldn't": "should not",
    "wasn't": "was not",
    "weren't": "were not",
    "won't": "will not",
    "wouldn't": "would not",
    "you're": "you are",
    "you've": "you have",
}

NEGATIONS = {
    "no",
    "not",
    "never",
    "neither",
    "nor",
    "cannot",
    "without",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


@dataclass
class NLPPreprocessor:
    """Production-friendly preprocessing for classical text sentiment models."""

    negation_window: int = 3
    stopwords: set[str] = field(default_factory=lambda: set(STOPWORDS) - NEGATIONS)

    def normalize_unicode(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    def remove_html(self, text: str) -> str:
        text = html.unescape(text)
        return re.sub(r"<[^>]+>", " ", text)

    def remove_urls(self, text: str) -> str:
        return re.sub(r"https?://\S+|www\.\S+", " ", text)

    def remove_emails(self, text: str) -> str:
        return re.sub(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", " ", text)

    def expand_contractions(self, text: str) -> str:
        for contraction, expanded in CONTRACTIONS.items():
            text = re.sub(rf"\b{re.escape(contraction)}\b", expanded, text, flags=re.IGNORECASE)
        return text

    def remove_numbers(self, text: str) -> str:
        return re.sub(r"\b\d+(?:\.\d+)?\b", " ", text)

    def remove_special_characters(self, text: str) -> str:
        return re.sub(r"[^a-zA-Z\s.!?']", " ", text)

    def remove_extra_spaces(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def sentence_tokenize(self, text: str) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def word_tokenize(self, sentence: str) -> List[str]:
        return re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", sentence.lower())

    def lemmatize(self, token: str) -> str:
        irregular = {"better": "good", "worse": "bad", "children": "child"}
        if token in irregular:
            return irregular[token]
        for suffix in ("ing", "ed", "ly", "es", "s"):
            if len(token) > len(suffix) + 2 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    def handle_negation(self, tokens: Iterable[str]) -> List[str]:
        processed: List[str] = []
        negate_for = 0
        for token in tokens:
            if token in NEGATIONS:
                processed.append(token)
                negate_for = self.negation_window
                continue
            processed.append(f"not_{token}" if negate_for else token)
            negate_for = max(0, negate_for - 1)
        return processed

    def preprocess(self, text: str) -> str:
        text = self.normalize_unicode(text)
        text = self.remove_html(text)
        text = self.remove_urls(text)
        text = self.remove_emails(text)
        text = self.expand_contractions(text)
        text = text.lower()
        text = self.remove_numbers(text)
        text = self.remove_special_characters(text)
        text = self.remove_extra_spaces(text)

        tokens: List[str] = []
        for sentence in self.sentence_tokenize(text):
            sentence_tokens = self.word_tokenize(sentence)
            sentence_tokens = [token for token in sentence_tokens if token not in self.stopwords]
            sentence_tokens = [self.lemmatize(token) for token in sentence_tokens]
            tokens.extend(self.handle_negation(sentence_tokens))
        return " ".join(tokens)

    def explain_steps(self) -> List[str]:
        return [
            "Unicode normalization",
            "HTML removal",
            "URL removal",
            "Email ID removal",
            "Contraction expansion",
            "Lowercasing",
            "Number removal",
            "Special character removal",
            "Extra space cleanup",
            "Sentence tokenization",
            "Word tokenization",
            "Stopword removal",
            "Lemmatization",
            "Negation handling",
        ]
