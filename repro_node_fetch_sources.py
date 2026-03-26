"""Reproduce the pipeline up to and including node_fetch_sources."""

import argparse
import json
import uuid

from src.agent.nodes import (
    node_check_permissions,
    node_fetch_sources,
    node_validate_request,
)
from src.agent.state import AgentState
from src.monitoring.callbacks import configure_logging


def run_until_fetch_sources(message: str, role: str, user_id: str, session_id: str) -> AgentState:
    """Run node_validate_request -> node_check_permissions -> node_fetch_sources."""
    state: AgentState = {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "raw_message": message,
        "publish": False,
        "fetched_articles": [],
        "filtered_articles": [],
        "rag_context": [],
    }

    state = node_validate_request(state)
    state = node_check_permissions(state)

    if state.get("permission_result") == "denied":
        return state

    state = node_fetch_sources(state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduce News Agent execution up to node_fetch_sources."
    )
    parser.add_argument(
        "--message",
        "-m",
        type=str,
        default="дай новости по AI и Python",
        help="User message to process",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Session ID (auto-generated if omitted)",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="demo_user",
        help="User ID",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="reader",
        choices=["reader", "viewer", "admin"],
        help="User role",
    )
    args = parser.parse_args()

    configure_logging()

    session_id = args.session_id or str(uuid.uuid4())
    result = run_until_fetch_sources(
        message=args.message,
        role=args.role,
        user_id=args.user_id,
        session_id=session_id,
    )

    print("\n=== Result after node_fetch_sources ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nFetched articles count: {len(result.get('fetched_articles', []))}")


if __name__ == "__main__":
    main()
