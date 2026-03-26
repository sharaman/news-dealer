"""MCP tool implementations for Telegram."""
import asyncio
import structlog
from src.sources.telegram import fetch_telegram_posts
from src.config import get_settings

logger = structlog.get_logger()


def get_telegram_posts_sync(channel: str, count: int = 5) -> list[dict]:
    """Sync wrapper for Telegram fetch (used by MCP server)."""
    settings = get_settings()
    allowed = settings.allowed_telegram_channels_list
    clean_channel = channel.lstrip("@").lower()
    if clean_channel not in [c.lower() for c in allowed]:
        logger.warning("channel_not_in_allowlist", requested=channel, allowed=allowed)
        clean_channel = allowed[0] if allowed else "durov"

    return asyncio.run(fetch_telegram_posts(clean_channel, count))
