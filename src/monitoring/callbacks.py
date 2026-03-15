import os
import structlog
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler  # noqa: F401
from langfuse import LangfuseOtelSpanAttributes
from opentelemetry import trace as otel_trace

logger = structlog.get_logger()


def get_langfuse_handler(session_id: str, user_id: str) -> LangfuseCallbackHandler | None:
    """Return a Langfuse v4 callback handler, or None if not configured.

    Langfuse v4: auth is configured via env vars (LANGFUSE_SECRET_KEY,
    LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST). session_id and user_id are attached
    as OpenTelemetry span attributes on the current span.
    """
    try:
        from src.config import get_settings
        settings = get_settings()
        if not settings.langfuse_secret_key or not settings.langfuse_public_key:
            logger.warning("langfuse_not_configured", session_id=session_id)
            return None

        # Propagate auth to env so Langfuse SDK picks it up automatically
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

        # Attach session / user context to the current OTEL span
        span = otel_trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(LangfuseOtelSpanAttributes.TRACE_SESSION_ID, session_id)
            span.set_attribute(LangfuseOtelSpanAttributes.TRACE_USER_ID, user_id)

        return LangfuseCallbackHandler()
    except Exception as exc:
        logger.error("langfuse_handler_error", error=str(exc))
        return None


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        logger_factory=structlog.PrintLoggerFactory(),
    )
