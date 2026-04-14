"""FinBERT sentiment scoring with Alpaca news headlines.
Cached per symbol for 5 minutes to avoid redundant model inference."""

import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

logger = logging.getLogger("options-bot.scanner.sentiment")

# Cache TTL: 5 minutes per symbol
CACHE_TTL_SECONDS = 300

# Lazy-loaded FinBERT pipeline (loaded once, reused across calls)
_finbert_pipeline = None
_cache: dict[str, tuple[float, "SentimentResult"]] = {}


@dataclass
class SentimentResult:
    """FinBERT sentiment for a symbol."""
    score: float        # -1.0 (bearish) to +1.0 (bullish)
    magnitude: float    # Confidence of the dominant sentiment (0 to 1)
    headline_count: int # Headlines analyzed
    strongest_headline: str  # Most directional headline (for logging)


def _get_finbert():
    """Lazy-load FinBERT pipeline. ~2s first call, instant after."""
    global _finbert_pipeline
    if _finbert_pipeline is None:
        from transformers import pipeline
        _finbert_pipeline = pipeline(
            "sentiment-analysis", model="ProsusAI/finbert", top_k=None
        )
        logger.info("FinBERT model loaded")
    return _finbert_pipeline


def _fetch_headlines(symbol: str, hours: int = 1) -> list[str]:
    """Fetch recent news headlines from Alpaca News API."""
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        api_secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY")
        if not api_key:
            return []

        client = NewsClient(api_key, api_secret)
        start = datetime.now(timezone.utc) - timedelta(hours=hours)
        req = NewsRequest(symbols=symbol, start=start, limit=20, sort="desc")
        result = client.get_news(req)
        # Alpaca NewsSet stores items in result.data["news"]
        news_list = result.data.get("news", []) if result and hasattr(result, "data") else []
        # Filter: only accept headlines where symbol is explicitly tagged AND
        # is a primary subject (<=3 total tagged symbols). Market-wide articles
        # with 10+ tickers are commentary, not symbol-specific catalysts.
        filtered = []
        for n in news_list:
            if not hasattr(n, "headline") or not n.headline:
                continue
            tags = n.symbols if hasattr(n, "symbols") else []
            if symbol in tags and len(tags) <= 3:
                filtered.append(n.headline)
        return filtered
    except Exception as e:
        logger.warning(f"News fetch failed for {symbol}: {e}")
        return []


def _score_headlines(headlines: list[str]) -> SentimentResult:
    """Score headlines with FinBERT. Returns aggregate sentiment."""
    if not headlines:
        return SentimentResult(score=0.0, magnitude=0.0, headline_count=0, strongest_headline="")

    pipe = _get_finbert()
    scores = []
    strongest_score = 0.0
    strongest_hl = ""

    for hl in headlines:
        result = pipe(hl)
        # result = [[{label, score}, ...]]
        probs = {r["label"]: r["score"] for r in result[0]}
        pos = probs.get("positive", 0)
        neg = probs.get("negative", 0)
        net = pos - neg  # -1 to +1

        scores.append(net)
        if abs(net) > abs(strongest_score):
            strongest_score = net
            strongest_hl = hl

    avg_score = sum(scores) / len(scores)
    magnitude = max(abs(s) for s in scores)

    return SentimentResult(
        score=round(avg_score, 4),
        magnitude=round(magnitude, 4),
        headline_count=len(headlines),
        strongest_headline=strongest_hl[:120],
    )


def get_sentiment(symbol: str) -> SentimentResult:
    """Get FinBERT sentiment for a symbol. Cached 5 minutes."""
    now = time.time()
    if symbol in _cache:
        cache_time, cached_result = _cache[symbol]
        if (now - cache_time) < CACHE_TTL_SECONDS:
            return cached_result

    headlines = _fetch_headlines(symbol, hours=1)
    result = _score_headlines(headlines)
    _cache[symbol] = (now, result)

    if result.headline_count > 0:
        logger.info(
            f"Sentiment {symbol}: score={result.score:+.3f} "
            f"mag={result.magnitude:.3f} headlines={result.headline_count}"
        )
    return result
