"""
Local Vector RAG Engine for Dynamic Profile Bullet & Project Selection.

Matches granular candidate achievements, projects, and work experience bullets
against target job descriptions using pure-Python TF-IDF vectorization and
cosine similarity, ensuring zero external dependencies and sub-10ms execution.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

# Standard technical stop words to ignore when vectorizing
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "will", "shall", "work", "working", "looking", "role",
    "candidate", "team", "experience", "years", "skills", "required", "requirements"
}


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric terms."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9_\+#\.\-]{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


def _compute_tf(tokens: list[str]) -> dict[str, float]:
    """Compute term frequency vector."""
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {word: count / total for word, count in counts.items()}


def _compute_idf(corpus: list[list[str]]) -> dict[str, float]:
    """Compute inverse document frequency across a corpus of documents."""
    num_docs = len(corpus)
    if num_docs == 0:
        return {}
    idf = {}
    all_words = set(word for doc in corpus for word in doc)
    for word in all_words:
        doc_count = sum(1 for doc in corpus if word in doc)
        idf[word] = math.log((1 + num_docs) / (1 + doc_count)) + 1.0
    return idf


def _tfidf_vector(tf: dict[str, float], idf: dict[str, float]) -> dict[str, float]:
    """Combine TF and IDF into a single weighted vector."""
    return {word: score * idf.get(word, 1.0) for word, score in tf.items()}


def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Calculate cosine similarity between two sparse term vectors."""
    common_words = set(vec1.keys()) & set(vec2.keys())
    if not common_words:
        return 0.0
    dot_product = sum(vec1[w] * vec2[w] for w in common_words)
    norm1 = math.sqrt(sum(v * v for v in vec1.values()))
    norm2 = math.sqrt(sum(v * v for v in vec2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


def rank_bullets_by_relevance(
    job_description: str,
    bullets: list[str | dict[str, Any]],
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """
    Ranks a list of profile bullets/projects by semantic relevance to a job description.

    Args:
        job_description: The job description text or posting requirements.
        bullets: A list of string bullets or dicts with 'text' / 'bullet' / 'description'.
        top_k: Maximum number of ranked results to return.

    Returns:
        A list of dicts with:
          - text: The original bullet text
          - score: Cosine similarity match score (0.0 to 1.0)
          - matched_keywords: List of matching technical keywords
          - rank: 1-indexed position
    """
    if not bullets or not job_description:
        return []

    # Normalize bullets to uniform string entries
    normalized: list[tuple[str, Any]] = []
    for item in bullets:
        if isinstance(item, str):
            text = item.strip()
            orig = item
        elif isinstance(item, dict):
            text = (item.get("text") or item.get("bullet") or item.get("description") or "").strip()
            orig = item
        else:
            text = str(item).strip()
            orig = item
        if text:
            normalized.append((text, orig))

    if not normalized:
        return []

    jd_tokens = _tokenize(job_description)
    if not jd_tokens:
        return [
            {"text": t, "original": o, "score": 0.0, "matched_keywords": [], "rank": i + 1}
            for i, (t, o) in enumerate(normalized[:top_k])
        ]

    corpus = [jd_tokens] + [_tokenize(t) for t, _ in normalized]
    idf = _compute_idf(corpus)

    jd_tf = _compute_tf(jd_tokens)
    jd_vec = _tfidf_vector(jd_tf, idf)

    scored: list[dict[str, Any]] = []
    jd_token_set = set(jd_tokens)

    for text, orig in normalized:
        b_tokens = _tokenize(text)
        b_tf = _compute_tf(b_tokens)
        b_vec = _tfidf_vector(b_tf, idf)
        score = _cosine_similarity(jd_vec, b_vec)
        matched = list(set(b_tokens) & jd_token_set)

        scored.append({
            "text": text,
            "original": orig,
            "score": round(score, 4),
            "matched_keywords": matched[:6],
        })

    # Sort descending by similarity score
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Assign 1-indexed rank
    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank

    return scored[:top_k]

