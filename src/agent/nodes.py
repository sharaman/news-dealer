"""LangGraph node implementations."""
import asyncio
import structlog
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import AgentState
from src.config import get_settings
from src.control_plane.validator import validate_request
from src.control_plane.policy import check_permissions
from src.data_plane.normalizer import normalize_text
from src.rag.store import seed_interests
from src.rag.retriever import retrieve_interests, filter_articles_by_interests
from src.monitoring.callbacks import get_langfuse_handler

logger = structlog.get_logger()


def node_validate_request(state: AgentState) -> AgentState:
    """Validate and normalize user request. Detect injection attempts."""
    settings = get_settings()
    raw = state.get("raw_message", "")

    normalized = normalize_text(raw)
    valid, reason = validate_request(normalized, settings.max_message_length)

    if not valid:
        logger.warning("request_invalid", reason=reason)
        return {
            **state,
            "normalized_message": normalized,
            "permission_result": "denied",
            "denial_reason": reason,
        }

    return {**state, "normalized_message": normalized}


def node_check_permissions(state: AgentState) -> AgentState:
    """Control Plane RBAC check — determine allowed sources."""
    if state.get("permission_result") == "denied":
        return state  # already rejected

    settings = get_settings()
    user_id = state.get("user_id", "anonymous")
    role = state.get("role", "reader")

    decision = check_permissions(
        user_id=user_id,
        role=role,
        allowed_medium_topics=settings.allowed_medium_topics_list,
        allowed_telegram_channels=settings.allowed_telegram_channels_list,
    )

    if not decision.allowed:
        return {
            **state,
            "permission_result": "denied",
            "denial_reason": decision.reason,
        }

    return {
        **state,
        "permission_result": "allowed",
        "allowed_medium_topics": decision.allowed_medium_topics,
        "allowed_telegram_channels": decision.allowed_telegram_channels,
        "max_articles": decision.max_articles,
    }


async def _fetch_all_sources(
    medium_topics: list[str],
    telegram_channels: list[str],
    max_articles: int,
    medium_sid: str = "",
) -> list[dict]:
    """Fetch from all allowed sources concurrently."""
    from src.sources.medium import fetch_medium_articles
    from src.sources.telegram import fetch_telegram_posts

    tasks = []
    per_source = max(2, max_articles // max(1, len(medium_topics) + len(telegram_channels)))

    for topic in medium_topics:
        tasks.append(fetch_medium_articles(topic, per_source, sid=medium_sid))
    for channel in telegram_channels:
        tasks.append(fetch_telegram_posts(channel, per_source))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    articles = []
    for r in results:
        if isinstance(r, list):
            articles.extend(r)
    return articles[:max_articles]


def node_fetch_sources(state: AgentState) -> AgentState:
    """Data Plane: fetch articles from MCP-approved sources."""
    settings = get_settings()
    medium_topics = state.get("allowed_medium_topics", [])
    telegram_channels = state.get("allowed_telegram_channels", [])
    max_articles = state.get("max_articles", 10)

    articles = asyncio.run(
        _fetch_all_sources(medium_topics, telegram_channels, max_articles, medium_sid=settings.medium_sid)
    )

    logger.info("sources_fetched", total=len(articles))
    return {**state, "fetched_articles": articles}


def node_rag_filter(state: AgentState) -> AgentState:
    """Retrieve user interests from ChromaDB and filter articles."""
    settings = get_settings()
    seed_interests(settings.chroma_persist_dir, settings.default_user_interests_list)

    query = state.get("normalized_message", "") + " " + " ".join(
        state.get("allowed_medium_topics", [])
    )
    interests = retrieve_interests(settings.chroma_persist_dir, query, n_results=5)
    articles = state.get("fetched_articles", [])
    filtered = filter_articles_by_interests(articles, interests)

    return {**state, "rag_context": interests, "filtered_articles": filtered}


def node_generate_post(state: AgentState) -> AgentState:
    """Generate a Telegram post from filtered articles using LLM."""
    settings = get_settings()
    articles = state.get("filtered_articles", [])
    interests = state.get("rag_context", [])
    session_id = state.get("session_id", "unknown")
    user_id = state.get("user_id", "unknown")

    if not articles:
        return {**state, "generated_post": "", "error": "Нет подходящих статей для генерации поста."}

    n = settings.max_articles_in_post

    def _source_label(a: dict) -> str:
        if a.get("source") == "telegram":
            return f"Telegram @{a.get('channel', 'unknown')}"
        return f"Medium / {a.get('topic', 'unknown')}"

    article_summaries = "\n\n".join(
        f"[{i+1}] {a['title']}\n"
        f"Источник: {_source_label(a)}\n"
        f"Ссылка: {a.get('url', '')}\n"
        f"{a['summary'][:300]}"
        for i, a in enumerate(articles[:n])
    )

    system_prompt = """Ты — редактор Telegram-канала о технологиях. Твоя задача: на основе предоставленных новостей написать короткий, информативный пост для публикации в Telegram.

Правила:
- Длина поста: 150-300 слов
- Используй эмодзи уместно
- Сделай заголовок привлекательным
- Кратко опиши 2-3 самые интересные новости
- После каждой новости ОБЯЗАТЕЛЬНО укажи источник в скобках: (Medium) или (Telegram @channel)
- Добавь призыв к действию в конце
- Пиши на русском языке"""

    user_prompt = f"""Интересы аудитории: {', '.join(interests)}

Свежие новости:
{article_summaries}

Напиши пост для Telegram-канала. Для каждой новости укажи источник."""

    callbacks = []
    handler = get_langfuse_handler(session_id, user_id)
    if handler:
        callbacks.append(handler)

    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
        callbacks=callbacks,
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        post = response.content

        # Детерминированно добавляем ссылки — не полагаемся на LLM
        sources_block = "\n\n📎 <b>Источники:</b>\n" + "\n".join(
            f"• <a href=\"{a.get('url', '')}\">({_source_label(a)}) {a['title'][:60]}</a>"
            for a in articles[:n]
            if a.get("url")
        )
        post = post + sources_block

        logger.info("post_generated", length=len(post), session_id=session_id)
        return {**state, "generated_post": post}
    except Exception as exc:
        logger.error("generation_error", error=str(exc))
        return {**state, "generated_post": "", "error": f"Ошибка генерации: {exc}"}


def node_validate_output(state: AgentState) -> AgentState:
    """Validate the generated post for safety and correctness."""
    post = state.get("generated_post", "")

    if not post or len(post.strip()) < 50:
        return {**state, "output_safe": False, "error": "Пост слишком короткий или пустой."}

    # Basic safety checks on output
    danger_phrases = ["ignore previous", "system prompt", "jailbreak", "as an AI, I cannot"]
    post_lower = post.lower()
    for phrase in danger_phrases:
        if phrase in post_lower:
            logger.warning("unsafe_output_detected", phrase=phrase)
            return {**state, "output_safe": False, "error": "Сгенерированный контент небезопасен."}

    return {**state, "output_safe": True, "final_response": post}


def node_publish_post(state: AgentState) -> AgentState:
    """Publish the generated post to Telegram if publish=True and bot is configured."""
    if not state.get("publish", False):
        return state

    settings = get_settings()
    bot_token = settings.telegram_bot_token
    channel = settings.telegram_publish_channel

    if not bot_token or not channel:
        logger.warning("publish_skipped_not_configured")
        return {**state, "published": False, "publish_error": "TELEGRAM_BOT_TOKEN или TELEGRAM_PUBLISH_CHANNEL не настроены."}

    from src.publisher.telegram import publish_to_telegram
    post = state.get("final_response", "")
    ok = asyncio.run(publish_to_telegram(post, bot_token, channel))

    if ok:
        return {**state, "published": True, "final_response": f"{post}\n\n✅ Опубликовано в {channel}"}
    return {**state, "published": False, "publish_error": "Ошибка отправки в Telegram."}


def node_error_handler(state: AgentState) -> AgentState:
    """Return a user-friendly error message."""
    denial = state.get("denial_reason", "")
    error = state.get("error", "")
    msg = denial or error or "Произошла неизвестная ошибка. Попробуйте переформулировать запрос."

    logger.warning("error_handled", message=msg, session_id=state.get("session_id"))
    return {**state, "final_response": f"❌ {msg}"}
