"""MCP tool implementations for Medium and Telegram."""
import asyncio
import structlog
from src.sources.medium import fetch_medium_articles
from src.sources.telegram import fetch_telegram_posts
from src.config import get_settings

logger = structlog.get_logger()


def get_medium_articles_sync(topic: str, count: int = 5) -> list[dict]:
    """Sync wrapper for Medium RSS fetch (used by MCP server)."""
    settings = get_settings()
    allowed = settings.allowed_medium_topics_list
    # Sanitize topic against allowlist
    safe_topic = topic.lower().replace(" ", "-")
    # Find closest match in allowed list
    matched = next((t for t in allowed if safe_topic in t or t in safe_topic), None)
    if not matched:
        # Use first allowed topic as fallback
        matched = allowed[0] if allowed else "artificial-intelligence"
        logger.warning("topic_not_in_allowlist", requested=topic, using=matched)

    return asyncio.run(fetch_medium_articles(matched, count, sid=settings.medium_sid))


def get_telegram_posts_sync(channel: str, count: int = 5) -> list[dict]:
    """Sync wrapper for Telegram fetch (used by MCP server)."""
    settings = get_settings()
    allowed = settings.allowed_telegram_channels_list
    clean_channel = channel.lstrip("@").lower()
    if clean_channel not in [c.lower() for c in allowed]:
        logger.warning("channel_not_in_allowlist", requested=channel, allowed=allowed)
        clean_channel = allowed[0] if allowed else "durov"

    return asyncio.run(fetch_telegram_posts(clean_channel, count))
