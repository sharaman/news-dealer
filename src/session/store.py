"""SQLite-backed session state via LangGraph SqliteSaver."""
from langgraph.checkpoint.sqlite import SqliteSaver
import structlog
import sqlite3

logger = structlog.get_logger()


def get_checkpointer(db_path: str) -> SqliteSaver:
    """Return a LangGraph SqliteSaver checkpointer backed by SQLite."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    logger.info("session_store_initialized", db_path=db_path)
    return checkpointer


def make_config(session_id: str, user_id: str) -> dict:
    """Build the LangGraph thread config for a given session."""
    return {
        "configurable": {
            "thread_id": session_id,
            "user_id": user_id,
        }
    }
