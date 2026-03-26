"""LangGraph node implementations."""
import asyncio
import re
from pathlib import Path
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


def _load_style_templates(templates_dir: str) -> list[str]:
    """Load all .txt style template files from the given directory."""
    path = Path(templates_dir)
    if not path.is_dir():
        logger.warning("style_templates_dir_not_found", path=str(path))
        return []
    templates = sorted(path.glob("*.txt"))
    examples = []
    for f in templates:
        try:
            examples.append(f.read_text(encoding="utf-8").strip())
        except OSError as exc:
            logger.warning("style_template_read_error", file=str(f), error=str(exc))
    logger.info("style_templates_loaded", count=len(examples), dir=str(path))
    return examples


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
        "allowed_telegram_channels": decision.allowed_telegram_channels,
        "max_articles": decision.max_articles,
    }


async def _fetch_all_sources(
    telegram_channels: list[str],
    max_articles: int,
) -> list[dict]:
    """Fetch from all allowed sources concurrently."""
    from src.sources.telegram import fetch_telegram_posts

    tasks = []
    per_source = max(2, max_articles // max(1, len(telegram_channels)))

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
    telegram_channels = state.get("allowed_telegram_channels", [])
    max_articles = state.get("max_articles", 10)

    articles = asyncio.run(_fetch_all_sources(telegram_channels, max_articles))

    logger.info("sources_fetched", total=len(articles))
    return {**state, "fetched_articles": articles}


def node_rag_filter(state: AgentState) -> AgentState:
    """Retrieve user interests from ChromaDB and filter articles."""
    settings = get_settings()
    seed_interests(settings.chroma_persist_dir, settings.default_user_interests_list)

    query = state.get("normalized_message", "")
    interests = retrieve_interests(settings.chroma_persist_dir, query, n_results=5)
    articles = state.get("fetched_articles", [])
    filtered = filter_articles_by_interests(articles, interests)

    return {**state, "rag_context": interests, "filtered_articles": filtered}


def _inject_inline_sources(post: str, articles: list[dict], source_label_fn) -> str:
    """Inject inline HTML source links after each numbered paragraph (1/, 2/, ...)."""
    lines = post.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        m = re.match(r"^(\d+)/", stripped)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(articles):
                article = articles[idx]
                url = article.get("url", "")
                label = source_label_fn(article)
                # Remove any existing source marker added by LLM.
                cleaned = re.sub(r"\s*\([^)]{1,40}\)\s*$", "", line.rstrip())
                if url:
                    line = f"{cleaned} [{label}] ({url})"
                else:
                    line = f"{cleaned} [{label}]"
        result.append(line)
    return "\n".join(result)


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
        return "Источник"

    article_summaries = "\n\n".join(
        f"[{i+1}] {a['title']}\n"
        f"Источник: {_source_label(a)}\n"
        f"Ссылка: {a.get('url', '')}\n"
        f"{a['summary'][:300]}"
        for i, a in enumerate(articles[:n])
    )

    style_examples = _load_style_templates(settings.style_templates_dir)

    style_section = ""
    if style_examples:
        joined = "\n\n---\n\n".join(style_examples)
        style_section = f"\n\nПримеры постов в нужном стиле (повтори структуру, тон и подачу):\n\n{joined}\n\n---"

    system_prompt = f"""Ты — редактор Telegram-канала о технологиях. Твоя задача: на основе предоставленных новостей написать пост в точно таком же стиле, как примеры ниже.{style_section}

Правила:
- Строго следуй стилю примеров: структура, тон, использование эмодзи, длина
- НЕ добавляй источники самостоятельно — они будут вставлены автоматически
- Пиши на русском языке"""

    user_prompt = f"""Интересы аудитории: {', '.join(interests)}

Свежие новости:
{article_summaries}

Напиши пост в стиле примеров."""

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

        # Детерминированно вставляем источники inline после каждого пронумерованного пункта
        post = _inject_inline_sources(post, articles[:n], _source_label)

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
