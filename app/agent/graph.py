from langgraph.graph import StateGraph, END

from app.agent.state import EODState
from app.agent.nodes import (
    fetch_activities,
    generate_draft,
    self_review,
    revise_draft,
)


def should_revise(state: EODState) -> str:
    """Conditional edge: revise or finalize."""
    if state.get("review_approved", False):
        return "finalize"
    if state.get("revision_count", 0) >= 2:
        return "finalize"
    return "revise"


def finalize(state: EODState) -> dict:
    """Copy approved draft to final_narrative."""
    return {"final_narrative": state["draft"]}


def build_eod_graph() -> StateGraph:
    graph = StateGraph(EODState)

    # Add nodes
    graph.add_node("fetch_activities", fetch_activities)
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("self_review", self_review)
    graph.add_node("revise_draft", revise_draft)
    graph.add_node("finalize", finalize)

    # Define edges
    graph.set_entry_point("fetch_activities")
    graph.add_edge("fetch_activities", "generate_draft")
    graph.add_edge("generate_draft", "self_review")

    # Conditional: review passes → finalize, fails → revise (cap at 2)
    graph.add_conditional_edges(
        "self_review",
        should_revise,
        {
            "finalize": "finalize",
            "revise": "revise_draft",
        },
    )
    graph.add_edge("revise_draft", "self_review")
    graph.add_edge("finalize", END)

    return graph.compile()


# Pre-compiled graph instance
eod_agent = build_eod_graph()
