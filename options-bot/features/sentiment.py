"""
Sentiment features for TSLA swing trading.

Fetches recent news headlines from Alpaca's News API and computes
sentiment scores using TextBlob. Produces features:
  - news_sentiment_score: average polarity of recent headlines (-1 to +1)
  - news_sentiment_magnitude: average subjectivity (0 to 1)
  - news_volume_24h: number of articles in last 24 hours
  - sentiment_momentum: current sentiment minus 3-day average

Data source: Alpaca News API (free with paper/live account).
Sentiment: TextBlob (available, no GPU needed).
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("options-bot.features.sentiment")


@dataclass
class SentimentFeatures:
    """Sentiment features for a symbol."""
    news_sentiment_score: float       # -1 to +1 (negative to positive)
    news_sentiment_magnitude: float   # 0 to 1 (objective to subjective)
    news_volume_24h: int              # article count
    sentiment_momentum: float         # current - 3d average
    headline_count: int               # total headlines analyzed


def compute_sentiment_features(
    symbol: str,
    lookback_hours: int = 24,
    lookback_days_for_momentum: int = 3,
) -> Optional[SentimentFeatures]:
    """
    Compute sentiment features from Alpaca news headlines.

    Args:
        symbol: Stock ticker (e.g. "TSLA")
        lookback_hours: Hours of recent news for current sentiment
        lookback_days_for_momentum: Days of news for momentum baseline

    Returns:
        SentimentFeatures or None if news unavailable.
    """
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        from textblob import TextBlob
    except ImportError as e:
        logger.warning(f"Sentiment dependencies unavailable: {e}")
        return None

    api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not api_secret:
        logger.warning("Sentiment: Alpaca credentials not available")
        return None

    try:
        client = NewsClient(api_key, api_secret)
        now = datetime.now(timezone.utc)

        # Fetch recent news (last N hours)
        recent_start = now - timedelta(hours=lookback_hours)
        recent_request = NewsRequest(
            symbols=symbol,
            start=recent_start,
            end=now,
            limit=50,
            sort="desc",
        )
        recent_response = client.get_news(recent_request)
        recent_news = recent_response.data.get('news', []) if hasattr(recent_response, 'data') and isinstance(recent_response.data, dict) else []

        # Fetch older news for momentum baseline
        baseline_start = now - timedelta(days=lookback_days_for_momentum)
        baseline_end = recent_start
        baseline_request = NewsRequest(
            symbols=symbol,
            start=baseline_start,
            end=baseline_end,
            limit=100,
            sort="desc",
        )
        baseline_response = client.get_news(baseline_request)
        baseline_news = baseline_response.data.get('news', []) if hasattr(baseline_response, 'data') and isinstance(baseline_response.data, dict) else []

        # Compute sentiment on recent headlines
        recent_polarities = []
        recent_subjectivities = []
        for article in recent_news:
            headline = getattr(article, 'headline', '') or ''
            summary = getattr(article, 'summary', '') or ''
            text = f"{headline}. {summary}".strip()
            if text and text != ".":
                blob = TextBlob(text)
                recent_polarities.append(blob.sentiment.polarity)
                recent_subjectivities.append(blob.sentiment.subjectivity)

        # Compute baseline sentiment
        baseline_polarities = []
        for article in baseline_news:
            headline = getattr(article, 'headline', '') or ''
            summary = getattr(article, 'summary', '') or ''
            text = f"{headline}. {summary}".strip()
            if text and text != ".":
                blob = TextBlob(text)
                baseline_polarities.append(blob.sentiment.polarity)

        # Aggregate
        import numpy as np
        current_sentiment = float(np.mean(recent_polarities)) if recent_polarities else 0.0
        current_magnitude = float(np.mean(recent_subjectivities)) if recent_subjectivities else 0.0
        baseline_sentiment = float(np.mean(baseline_polarities)) if baseline_polarities else 0.0
        momentum = current_sentiment - baseline_sentiment

        result = SentimentFeatures(
            news_sentiment_score=current_sentiment,
            news_sentiment_magnitude=current_magnitude,
            news_volume_24h=len(recent_polarities),
            sentiment_momentum=momentum,
            headline_count=len(recent_polarities) + len(baseline_polarities),
        )

        logger.info(
            f"Sentiment({symbol}): score={current_sentiment:.3f} "
            f"magnitude={current_magnitude:.3f} volume={len(recent_polarities)} "
            f"momentum={momentum:+.3f} (baseline from {len(baseline_polarities)} articles)"
        )

        return result

    except Exception as e:
        logger.error(f"Sentiment computation failed for {symbol}: {e}", exc_info=True)
        return None
