"""
news_retriever.py
-----------------
NewsAPI client for fetching articles by topic. Uses the "everything" endpoint
with configurable parameters for date range, language, and sorting.

Derived from Lab 4 — adapted for the unified IntelliDigest pipeline.
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"
DEFAULT_PAGE_SIZE = 10
DEFAULT_SORT_BY = "publishedAt"


class NewsRetriever:
    """Retrieves news articles from NewsAPI."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        if not self.api_key:
            raise ValueError(
                "NewsAPI key is required. Set NEWSAPI_KEY in your .env file "
                "or pass it directly."
            )

    def search_articles(
        self,
        query: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        sort_by: str = DEFAULT_SORT_BY,
        from_date: str | None = None,
        to_date: str | None = None,
        language: str = "en",
    ) -> list[dict]:
        """Search for news articles matching a query."""
        if not from_date:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

        params = {
            "q": query,
            "pageSize": min(page_size, 100),
            "sortBy": sort_by,
            "from": from_date,
            "to": to_date,
            "language": language,
            "apiKey": self.api_key,
        }

        response = requests.get(NEWSAPI_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            raise RuntimeError(
                f"NewsAPI error: {data.get('message', 'Unknown error')}"
            )

        return self._parse_articles(data.get("articles", []))

    @staticmethod
    def _parse_articles(raw_articles: list[dict]) -> list[dict]:
        """Normalize raw API responses into clean dicts."""
        parsed = []
        for article in raw_articles:
            if article.get("title") == "[Removed]" or not article.get("title"):
                continue
            parsed.append({
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "content": article.get("content", ""),
                "url": article.get("url", ""),
                "source": article.get("source", {}).get("name", "Unknown"),
                "published_at": article.get("publishedAt", ""),
                "author": article.get("author", "Unknown"),
            })
        return parsed
