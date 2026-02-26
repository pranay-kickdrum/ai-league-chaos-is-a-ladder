"""LangGraph StateGraph — connects all agents into a workflow."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.agents.coordinator import checkpoint_1, checkpoint_2, checkpoint_3, finalize
from app.agents.optimizer import optimize
from app.agents.planner import plan
from app.agents.replanner import replan
from app.agents.researcher import research
from app.agents.verifier import verify
from app.models.agent_state import TripState

logger = logging.getLogger(__name__)


# ── Router — determines where to start/resume ────────────────────

async def _router(state: TripState) -> TripState:
    """Pass-through node. Routing is handled by _route_entry conditional edge."""
    return state


def _route_entry(state: TripState) -> str:
    """Decide where to start based on checkpoint state (fresh start vs resume)."""

    # If replan already ran (called directly by /replan endpoint), route based on delta
    replan_delta = state.get("replan_delta")
    if replan_delta and isinstance(replan_delta, dict):
        # Clear so we don't re-trigger on subsequent passes
        if replan_delta.get("re_research_needed"):
            logger.info("Router: replan delta requires re-research → do_research")
            return "do_research"
        logger.info("Router: replan delta → plan")
        return "plan"

    last_cp = state.get("last_checkpoint", "")
    decision = state.get("checkpoint_decision", {})
    if isinstance(decision, dict):
        action = decision.get("action", "")
        decision_cp = decision.get("checkpoint", "")
    else:
        action = getattr(decision, "action", "")
        decision_cp = getattr(decision, "checkpoint", "")

    # Use the decision's checkpoint if present, fallback to last_checkpoint
    cp = decision_cp or last_cp

    if not cp:
        # Fresh start — run full pipeline
        return "do_research"

    logger.info("Resuming from checkpoint %s with action %s", cp, action)

    if cp == "cp1":
        if action == "cancel":
            return END
        if action == "regenerate":
            return "plan"
        if action == "adjust_preferences":
            return "do_research"
        # Default: approved plan → proceed to CP2
        return "checkpoint_2"

    if cp == "cp2":
        if action == "cancel":
            return END
        if action == "request_changes":
            return "replan"
        # Default: approved budget → proceed to verify
        return "verify"

    if cp == "cp3":
        if action == "cancel":
            return END
        if action == "request_changes":
            return "replan"
        # Default: confirmed booking → finalize
        return "finalize"

    # Unknown checkpoint — start fresh
    return "do_research"


# ── Routing Functions ─────────────────────────────────────────────

def _after_checkpoint_1(state: TripState) -> str:
    """Route after checkpoint 1 (plan direction): check human decision."""
    decision = state.get("checkpoint_decision", {})
    if isinstance(decision, dict):
        action = decision.get("action", "")
    else:
        action = getattr(decision, "action", "")

    if action == "cancel":
        return END
    if action == "regenerate":
        return "plan"
    if action == "adjust_preferences":
        return "do_research"
    # User selected a plan → show budget approval
    return "checkpoint_2"


def _after_checkpoint_2(state: TripState) -> str:
    """Route after checkpoint 2 (budget approval): check human decision."""
    decision = state.get("checkpoint_decision", {})
    if isinstance(decision, dict):
        action = decision.get("action", "")
    else:
        action = getattr(decision, "action", "")

    if action == "cancel":
        return END
    if action == "request_changes":
        return "replan"
    return "verify"


def _after_checkpoint_3(state: TripState) -> str:
    """Route after checkpoint 3: check human decision."""
    decision = state.get("checkpoint_decision", {})
    if isinstance(decision, dict):
        action = decision.get("action", "")
    else:
        action = getattr(decision, "action", "")

    if action == "cancel":
        return END
    if action == "request_changes":
        return "replan"
    return "finalize"


def _after_replan(state: TripState) -> str:
    """Route after re-planning: check if re-research is needed."""
    delta = state.get("replan_delta", {})
    if isinstance(delta, dict) and delta.get("re_research_needed"):
        return "do_research"
    return "plan"


# ── Graph Builder ─────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""

    graph = StateGraph(TripState)

    # Add nodes
    graph.add_node("router", _router)
    graph.add_node("do_research", research)
    graph.add_node("checkpoint_1", checkpoint_1)
    graph.add_node("plan", plan)
    graph.add_node("optimize", optimize)
    graph.add_node("checkpoint_2", checkpoint_2)
    graph.add_node("verify", verify)
    graph.add_node("checkpoint_3", checkpoint_3)
    graph.add_node("finalize", finalize)
    graph.add_node("replan", replan)

    # Entry point is the router
    graph.set_entry_point("router")

    # Router dispatches to the correct node based on checkpoint state
    graph.add_conditional_edges(
        "router",
        _route_entry,
        {
            "do_research": "do_research",
            "plan": "plan",
            "checkpoint_2": "checkpoint_2",
            "verify": "verify",
            "replan": "replan",
            "finalize": "finalize",
            END: END,
        },
    )

    # Normal flow edges
    graph.add_edge("do_research", "plan")
    graph.add_edge("plan", "optimize")
    graph.add_edge("optimize", "checkpoint_1")

    # CP1: Trip understanding + plan selection
    graph.add_conditional_edges(
        "checkpoint_1",
        _after_checkpoint_1,
        {"checkpoint_2": "checkpoint_2", "plan": "plan", "do_research": "do_research", END: END},
    )

    # CP2: Budget approval
    graph.add_conditional_edges(
        "checkpoint_2",
        _after_checkpoint_2,
        {"verify": "verify", "replan": "replan", END: END},
    )

    graph.add_edge("verify", "checkpoint_3")

    graph.add_conditional_edges(
        "checkpoint_3",
        _after_checkpoint_3,
        {"finalize": "finalize", "replan": "replan", END: END},
    )

    graph.add_edge("finalize", END)

    graph.add_conditional_edges(
        "replan",
        _after_replan,
        {"do_research": "do_research", "plan": "plan"},
    )

    return graph


# Compiled graph singleton
_compiled_graph = None


def get_compiled_graph():
    """Get or create the compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph
