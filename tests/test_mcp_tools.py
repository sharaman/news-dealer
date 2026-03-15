"""Tests for MCP tool source fetching."""
import pytest
from unittest.mock import patch, AsyncMock
from src.sources.medium import fetch_medium_articles
from src.sources.telegram import fetch_telegram_posts


class TestMediumFetch:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """fetch_medium_articles returns a list (may be empty on network error)."""
        with patch("src.sources.medium.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Test AI Article</title>
      <link>https://medium.com/test</link>
      <description>Test description about AI</description>
    </item>
  </channel>
</rss>"""
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await fetch_medium_articles("artificial-intelligence", count=1)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        """On network error, returns empty list instead of raising."""
        import httpx
        with patch("src.sources.medium.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            result = await fetch_medium_articles("ai", count=3)
            assert result == []


class TestTelegramFetch:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        """fetch_telegram_posts returns a list."""
        with patch("src.sources.telegram.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = """
<html><body>
<div class="tgme_widget_message_text">Test post about AI and machine learning</div>
<div class="tgme_widget_message_text">Another post about Python</div>
</body></html>"""
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            result = await fetch_telegram_posts("test_channel", count=2)
            assert isinstance(result, list)
            assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self):
        """On network error, returns empty list."""
        import httpx
        with patch("src.sources.telegram.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            result = await fetch_telegram_posts("test_channel", count=3)
            assert result == []


# Import needed for mock
from unittest.mock import MagicMock
