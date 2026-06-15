"""Keyword extraction using simple frequency + heuristics."""
import re
from collections import Counter
from loguru import logger


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """
    Extract top N keywords from text using simple tokenization.
    Returns list of keyword strings.
    """
    # Simple tokenization — remove short words, numbers, common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "and", "but", "or", "yet", "so", "if",
        "because", "although", "though", "while", "where", "when", "that",
        "which", "who", "whom", "whose", "what", "this", "these", "those",
        "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
        "them", "my", "your", "his", "its", "our", "their", "mine", "yours",
        "hers", "ours", "theirs", "myself", "yourself", "himself", "herself",
        "itself", "ourselves", "yourselves", "themselves",
    }

    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    filtered = [w for w in words if w not in stop_words]
    counts = Counter(filtered)
    top = [word for word, _ in counts.most_common(top_n)]
    logger.info(f"Extracted {len(top)} keywords")
    return top
