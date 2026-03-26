from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o")

    # Langfuse
    langfuse_secret_key: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    # MCP Server
    mcp_server_host: str = Field(default="localhost")
    mcp_server_port: int = Field(default=8000)

    # Allowed sources (immutable — never changed by user)
    allowed_telegram_channels: str = Field(default="tlgur,ai_newz")

    # RAG
    chroma_persist_dir: str = Field(default="./chroma_db")

    # Session
    sqlite_db_path: str = Field(default="./sessions.db")

    # Default user interests
    default_user_interests: str = Field(default="AI,machine learning,Python,LLM,neural networks")

    # Telegram publishing
    telegram_bot_token: str = Field(default="")
    telegram_publish_channel: str = Field(default="")

    # Post generation
    max_articles_in_post: int = Field(default=5)
    style_templates_dir: str = Field(default="./style_templates")

    # Security
    max_message_length: int = Field(default=1000)

    @property
    def allowed_telegram_channels_list(self) -> list[str]:
        return [c.strip() for c in self.allowed_telegram_channels.split(",") if c.strip()]

    @property
    def default_user_interests_list(self) -> list[str]:
        return [i.strip() for i in self.default_user_interests.split(",") if i.strip()]

    @property
    def mcp_server_url(self) -> str:
        return f"http://{self.mcp_server_host}:{self.mcp_server_port}/sse"


@lru_cache
def get_settings() -> Settings:
    return Settings()
