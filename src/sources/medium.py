"""Medium.com RSS reader."""
import re
import feedparser
import structlog
import httpx

logger = structlog.get_logger()

MEDIUM_RSS_URL = "https://medium.com/feed/tag/{topic}"


def _build_medium_headers(sid: str = "") -> dict:
    """Build HTTP headers for Medium requests, optionally with auth cookie."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsAgent/1.0; RSS reader)"}
    if sid:
        headers["Cookie"] = f"sid={sid}"
    return headers


async def fetch_medium_articles(topic: str, count: int = 5, sid: str = "") -> list[dict]:
    """Fetch articles from Medium.com RSS for a given topic tag.

    Args:
        topic: Medium tag (e.g. 'artificial-intelligence')
        count: Max number of articles to return
        sid: Optional Medium session cookie value for authenticated access
    """
    url = MEDIUM_RSS_URL.format(topic=topic.lower().replace(" ", "-"))
    logger.info("fetching_medium", topic=topic, url=url, authenticated=bool(sid))

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=_build_medium_headers(sid))
            response.raise_for_status()
            feed = feedparser.parse(response.text)
    except httpx.HTTPError as exc:
        logger.error("medium_fetch_error", topic=topic, error=str(exc))
        return []

    articles = []
    for entry in feed.entries[:count]:
        summary = entry.get("summary", "")
        summary = re.sub(r"<[^>]+>", "", summary)[:500]

        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": summary,
            "source": "medium",
            "topic": topic,
        })

    logger.info("medium_articles_fetched", topic=topic, count=len(articles))
    return articles
