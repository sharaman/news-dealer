"""Stateless Data Plane executor — runs the LangGraph agent for a session."""
import structlog
from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.session.store import get_checkpointer, make_config
from src.config import get_settings

logger = structlog.get_logger()


def run_agent(
    message: str,
    session_id: str,
    user_id: str = "anonymous",
    role: str = "reader",
    publish: bool = False,
) -> str:
    """Execute the agent graph for a user message. Returns the final response."""
    settings = get_settings()
    checkpointer = get_checkpointer(settings.sqlite_db_path)
    graph = build_graph(checkpointer=checkpointer)
    config = make_config(session_id, user_id)

    initial_state: AgentState = {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "raw_message": message,
        "publish": publish,
        "fetched_articles": [],
        "filtered_articles": [],
        "rag_context": [],
    }

    logger.info("agent_run_start", session_id=session_id, user_id=user_id)

    try:
        result = graph.invoke(initial_state, config=config)
        response = result.get("final_response", "Нет ответа.")
        logger.info("agent_run_complete", session_id=session_id, response_length=len(response))
        return response
    except Exception as exc:
        logger.error("agent_run_error", session_id=session_id, error=str(exc))
        return f"❌ Внутренняя ошибка агента: {exc}"
