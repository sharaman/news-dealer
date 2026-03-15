"""Telegram Bot API publisher."""
import httpx
import structlog

logger = structlog.get_logger()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def publish_to_telegram(text: str, bot_token: str, channel: str) -> bool:
    """Send a message to a Telegram channel via Bot API.

    Args:
        text: Message text (supports HTML formatting)
        bot_token: Telegram bot token from @BotFather
        channel: Channel username (@channel) or numeric ID (-1001234567890)

    Returns:
        True if published successfully, False otherwise.
    """
    url = TELEGRAM_API_URL.format(token=bot_token)
    payload = {
        "chat_id": channel,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    logger.info("publishing_to_telegram", channel=channel, text_length=len(text))

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            data = response.json()

        if response.status_code == 200 and data.get("ok"):
            message_id = data.get("result", {}).get("message_id")
            logger.info("telegram_published", channel=channel, message_id=message_id)
            return True

        error = data.get("description", "unknown error")
        logger.error("telegram_publish_failed", channel=channel, status=response.status_code, error=error)
        return False

    except httpx.HTTPError as exc:
        logger.error("telegram_publish_error", channel=channel, error=str(exc))
        return False
