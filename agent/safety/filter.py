"""
Information filtering and source relevance scoring.
Filters out noisy, low-quality, paywalled, or irrelevant search results and scraped content.
"""

import re
from typing import List, Set
from urllib.parse import urlparse
from agent.models import SourceReference


class InformationFilter:
    """Scores, deduplicates, and filters retrieved information sources."""

    ERROR_PAGE_SIGNALS = [
        "403 forbidden",
        "access denied",
        "404 not found",
        "please enable cookies",
        "turn on javascript",
        "verify you are human",
        "cloudflare ray id",
        "just a moment...",
        "security check",
        "captcha",
    ]

    STOPWORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
        "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
        "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
        "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
        "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
        "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
        "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "s", "same", "she",
        "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
        "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
        "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
        "why", "with", "would", "you", "your", "yours", "yourself", "yourselves"
    }

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Normalizes URLs for deduplication."""
        try:
            parsed = urlparse(url.strip())
            # Lowercase netloc and strip trailing slash from path
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
        except Exception:
            return url.strip().lower()

    @classmethod
    def is_error_or_blocked_page(cls, text: str) -> bool:
        """Detects if a retrieved snippet or page is just a bot block or error page."""
        lower_text = text.lower()
        if len(text.strip()) < 15:
            return True
        for signal in cls.ERROR_PAGE_SIGNALS:
            if signal in lower_text:
                return True
        return False

    @classmethod
    def compute_lexical_relevance(cls, query: str, content: str) -> float:
        """
        Computes normalized Jaccard-like keyword overlap score between query and content.
        Scale: 0.0 to 1.0.
        """
        def tokenize(s: str) -> Set[str]:
            words = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", s.lower())
            return {w for w in words if w not in cls.STOPWORDS}

        query_tokens = tokenize(query)
        if not query_tokens:
            return 0.5  # neutral fallback if query has no content words

        content_tokens = tokenize(content)
        if not content_tokens:
            return 0.0

        overlap = query_tokens.intersection(content_tokens)
        score = len(overlap) / len(query_tokens)
        return min(1.0, max(0.0, score))

    @classmethod
    def filter_and_rank_sources(
        cls,
        sources: List[SourceReference],
        query: str,
        min_relevance: float = 0.25,
        max_sources: int = 6
    ) -> List[SourceReference]:
        """
        Deduplicates, scores, filters out low-quality/error pages, and ranks sources.
        """
        seen_urls = set()
        valid_sources: List[SourceReference] = []

        for src in sources:
            norm_url = cls.normalize_url(src.url)
            if norm_url in seen_urls:
                continue

            # Check for error / blocking page
            combined_text = f"{src.title} {src.snippet}"
            if cls.is_error_or_blocked_page(combined_text):
                continue

            # Compute relevance score
            relevance = cls.compute_lexical_relevance(query, combined_text)
            src.relevance_score = round(relevance, 2)

            if relevance >= min_relevance or len(valid_sources) < 2:
                # Keep if it meets threshold, or keep at least top 2 if available to prevent empty context
                seen_urls.add(norm_url)
                valid_sources.append(src)

        # Sort by relevance score descending
        valid_sources.sort(key=lambda s: s.relevance_score, reverse=True)

        # Re-index source IDs sequentially ([S1], [S2], ...)
        for idx, src in enumerate(valid_sources[:max_sources], start=1):
            src.source_id = f"S{idx}"

        return valid_sources[:max_sources]
