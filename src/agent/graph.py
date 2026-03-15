"""LangGraph StateGraph with conditional branching."""
from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes import (
    node_validate_request,
    node_check_permissions,
    node_fetch_sources,
    node_rag_filter,
    node_generate_post,
    node_validate_output,
    node_publish_post,
    node_error_handler,
)
import structlog

logger = structlog.get_logger()


def _route_after_permissions(state: AgentState) -> str:
    """Branch 1: denied → error_handler, allowed → fetch_sources."""
    if state.get("permission_result") == "denied":
        return "error_handler"
    return "fetch_sources"


def _route_after_fetch(state: AgentState) -> str:
    """Branch 2: no articles → error_handler, has articles → rag_filter."""
    articles = state.get("fetched_articles", [])
    if not articles:
        return "error_handler"
    return "rag_filter"


def _route_after_validate_output(state: AgentState) -> str:
    """Branch 3: unsafe output → error_handler, safe → publish_post."""
    if not state.get("output_safe", False):
        return "error_handler"
    return "publish_post"


def build_graph(checkpointer=None) -> StateGraph:
    """Build and compile the LangGraph agent."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("validate_request", node_validate_request)
    graph.add_node("check_permissions", node_check_permissions)
    graph.add_node("fetch_sources", node_fetch_sources)
    graph.add_node("rag_filter", node_rag_filter)
    graph.add_node("generate_post", node_generate_post)
    graph.add_node("validate_output", node_validate_output)
    graph.add_node("publish_post", node_publish_post)
    graph.add_node("error_handler", node_error_handler)

    # Linear edges
    graph.set_entry_point("validate_request")
    graph.add_edge("validate_request", "check_permissions")
    graph.add_edge("rag_filter", "generate_post")
    graph.add_edge("generate_post", "validate_output")
    graph.add_edge("publish_post", END)
    graph.add_edge("error_handler", END)

    # Conditional edges (branching points)
    graph.add_conditional_edges(
        "check_permissions",
        _route_after_permissions,
        {"error_handler": "error_handler", "fetch_sources": "fetch_sources"},
    )
    graph.add_conditional_edges(
        "fetch_sources",
        _route_after_fetch,
        {"error_handler": "error_handler", "rag_filter": "rag_filter"},
    )
    graph.add_conditional_edges(
        "validate_output",
        _route_after_validate_output,
        {"error_handler": "error_handler", "publish_post": "publish_post"},
    )

    return graph.compile(checkpointer=checkpointer)
