"""
News intelligence service.
Primary source: NewsAPI.org
Secondary source: Alpha Vantage NEWS_SENTIMENT
Sentiment + category: Claude Haiku batch classification (one API call per symbol refresh).
Results cached in news_items table (stale after 1 hour).
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx

from app.core.config import get_settings
from app.db.repositories.intelligence import NewsRepo

logger = logging.getLogger(__name__)
_settings = get_settings()

_CACHE_TTL = timedelta(hours=1)
_NEWSAPI_BASE = "https://newsapi.org/v2"
_AV_BASE = "https://www.alphavantage.co/query"


@dataclass
class NewsItem:
    symbol: str
    headline: str
    summary: str | None
    source: str
    url: str | None
    sentiment: str | None    # positive | negative | neutral
    category: str | None     # earnings | regulatory | political | product | macro | other
    published_at: str        # ISO datetime string

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "headline": self.headline,
            "summary": self.summary,
            "source": self.source,
            "url": self.url,
            "sentiment": self.sentiment,
            "category": self.category,
            "published_at": self.published_at,
        }


async def _fetch_newsapi(symbol: str, days: int, limit: int) -> list[dict]:
    if not _settings.news_api_key:
        return []
    from_date = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%d")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_NEWSAPI_BASE}/everything",
                params={
                    "q": f"{symbol} stock",
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "pageSize": min(limit * 2, 100),
                    "language": "en",
                    "apiKey": _settings.news_api_key,
                },
            )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {
                "headline": a.get("title", "").strip(),
                "summary": a.get("description"),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "url": a.get("url"),
                "published_at": a.get("publishedAt", ""),
            }
            for a in articles
            if a.get("title") and "[Removed]" not in (a.get("title") or "")
        ]
    except Exception as exc:
        logger.warning("NewsAPI fetch failed for %s: %s", symbol, exc)
        return []


async def _fetch_alpha_vantage(symbol: str) -> list[dict]:
    if not _settings.alpha_vantage_key:
        return []
    # Strip exchange suffix for AV (RELIANCE.NS → RELIANCE)
    av_ticker = symbol.split(".")[0] if "." in symbol else symbol
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _AV_BASE,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": av_ticker,
                    "limit": 50,
                    "apikey": _settings.alpha_vantage_key,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        if "feed" not in data:
            return []
        return [
            {
                "headline": it.get("title", "").strip(),
                "summary": it.get("summary"),
                "source": it.get("source", "Alpha Vantage"),
                "url": it.get("url"),
                "published_at": it.get("time_published", ""),
            }
            for it in data["feed"]
            if it.get("title")
        ]
    except Exception as exc:
        logger.warning("Alpha Vantage fetch failed for %s: %s", symbol, exc)
        return []


async def _classify_batch(symbol: str, articles: list[dict]) -> list[dict]:
    """
    Send all headlines in a single Claude Haiku call.
    Returns articles with sentiment + category fields added.
    Falls back to neutral/other if API call fails.
    """
    if not _settings.anthropic_api_key or not articles:
        return [{**a, "sentiment": "neutral", "category": "other"} for a in articles]

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=_settings.anthropic_api_key)
        headline_list = "\n".join(
            f"{i + 1}. {a['headline']}" for i, a in enumerate(articles)
        )
        prompt = (
            f"Classify each news headline about the stock ticker {symbol}.\n\n"
            f"Headlines:\n{headline_list}\n\n"
            "For each headline, return:\n"
            '- sentiment: "positive", "negative", or "neutral"\n'
            '- category: "earnings", "regulatory", "political", "product", "macro", or "other"\n\n'
            "Respond ONLY with a JSON array, one element per headline, in the same order:\n"
            '[{"sentiment": "...", "category": "..."}, ...]'
        )
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end <= 0:
            raise ValueError("No JSON array found in Haiku response")
        classifications = json.loads(text[start:end])

        result = []
        for i, article in enumerate(articles):
            cls = classifications[i] if i < len(classifications) else {}
            result.append(
                {
                    **article,
                    "sentiment": cls.get("sentiment", "neutral"),
                    "category": cls.get("category", "other"),
                }
            )
        return result
    except Exception as exc:
        logger.warning("Sentiment classification failed: %s", exc)
        return [{**a, "sentiment": "neutral", "category": "other"} for a in articles]


def _parse_published_at(raw: str) -> datetime:
    """Parse datetime strings from NewsAPI and Alpha Vantage; falls back to now()."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",   # NewsAPI: 2024-06-01T12:34:00Z
        "%Y%m%dT%H%M%S",         # Alpha Vantage: 20240601T123400
        "%Y-%m-%dT%H:%M:%S%z",  # RFC 3339 with offset
        "%Y-%m-%dT%H:%M:%S",    # no timezone
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc)


async def get_news(
    symbol: str,
    exchange: str,
    days: int,
    limit: int,
    pool: asyncpg.Pool,
) -> list[NewsItem]:
    repo = NewsRepo(pool)
    sym = symbol.upper()

    last_fetch = await repo.latest_fetch_time(sym)
    if last_fetch:
        age = datetime.now(timezone.utc) - last_fetch
        if age < _CACHE_TTL:
            rows = await repo.get_by_symbol(sym, days=days, limit=limit)
            return [
                NewsItem(
                    symbol=r["symbol"],
                    headline=r["headline"],
                    summary=r["summary"],
                    source=r["source"],
                    url=r["url"],
                    sentiment=r["sentiment"],
                    category=r["category"],
                    published_at=r["published_at"].isoformat(),
                )
                for r in rows
            ]

    # Fetch from both sources
    newsapi_articles = await _fetch_newsapi(sym, days=days, limit=limit)
    av_articles = await _fetch_alpha_vantage(sym)

    # Deduplicate by headline (lowercase)
    seen: set[str] = set()
    raw: list[dict] = []
    for a in [*newsapi_articles, *av_articles]:
        key = a["headline"].lower()
        if a["headline"] and key not in seen:
            seen.add(key)
            raw.append(a)

    raw = raw[:limit]
    if not raw:
        return []

    classified = await _classify_batch(sym, raw)

    to_save = [
        {
            "symbol": sym,
            "headline": a["headline"],
            "summary": a.get("summary"),
            "source": a["source"],
            "url": a.get("url"),
            "sentiment": a.get("sentiment", "neutral"),
            "category": a.get("category", "other"),
            "published_at": _parse_published_at(a.get("published_at", "")),
        }
        for a in classified
    ]

    await repo.bulk_upsert(to_save)

    return [
        NewsItem(
            symbol=it["symbol"],
            headline=it["headline"],
            summary=it["summary"],
            source=it["source"],
            url=it["url"],
            sentiment=it["sentiment"],
            category=it["category"],
            published_at=it["published_at"].isoformat(),
        )
        for it in to_save
    ]
