"""FastMCP SSE server exposing Telegram tools."""
from mcp.server.fastmcp import FastMCP
from src.mcp_server.tools import get_telegram_posts_sync
from src.monitoring.callbacks import configure_logging
import structlog

configure_logging()
logger = structlog.get_logger()

mcp = FastMCP("news-agent", stateless_http=True)


@mcp.tool()
def fetch_telegram_posts(channel: str, count: int = 5) -> list[dict]:
    """Fetch recent posts from a public Telegram channel.

    Args:
        channel: Telegram channel username (e.g. 'tlgur')
        count: Number of posts to return (max 10)
    """
    count = min(count, 10)
    logger.info("mcp_fetch_telegram", channel=channel, count=count)
    return get_telegram_posts_sync(channel, count)


if __name__ == "__main__":
    from src.config import get_settings
    settings = get_settings()
    logger.info("mcp_server_starting", host=settings.mcp_server_host, port=settings.mcp_server_port)
    mcp.run(transport="sse", host=settings.mcp_server_host, port=settings.mcp_server_port)
