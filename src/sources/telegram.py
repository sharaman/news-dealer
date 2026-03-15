"""Telegram public channel RSS reader via t.me/s/{channel}."""
import httpx
import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

TELEGRAM_WEB_URL = "https://t.me/s/{channel}"


async def fetch_telegram_posts(channel: str, count: int = 5) -> list[dict]:
    """Fetch recent posts from a public Telegram channel via the web preview."""
    url = TELEGRAM_WEB_URL.format(channel=channel.lstrip("@"))
    logger.info("fetching_telegram", channel=channel, url=url)

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NewsAgent/1.0)",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("telegram_fetch_error", channel=channel, error=str(exc))
        return []

    soup = BeautifulSoup(response.text, "lxml")
    messages = soup.select(".tgme_widget_message_text")

    posts = []
    for msg in messages[-count:]:
        text = msg.get_text(separator=" ", strip=True)
        if not text:
            continue
        posts.append({
            "title": text[:80] + ("..." if len(text) > 80 else ""),
            "url": url,
            "summary": text[:500],
            "source": "telegram",
            "channel": channel,
        })

    posts.reverse()  # newest first
    logger.info("telegram_posts_fetched", channel=channel, count=len(posts))
    return posts
