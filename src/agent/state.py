"""LangGraph AgentState definition."""
from typing import Literal
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    session_id: str
    user_id: str
    role: str

    # Input
    raw_message: str
    normalized_message: str

    # Control Plane decision
    permission_result: Literal["allowed", "denied"]
    denial_reason: str
    allowed_telegram_channels: list[str]
    max_articles: int

    # Fetched content
    fetched_articles: list[dict]

    # RAG
    rag_context: list[str]
    filtered_articles: list[dict]

    # Generation
    generated_post: str
    output_safe: bool

    # Publishing
    publish: bool
    published: bool
    publish_error: str

    # Final
    final_response: str
    error: str
