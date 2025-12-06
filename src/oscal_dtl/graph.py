# src/oscal_dtl/graph.py
"""LangGraph definition for OSCAL Digital Twin workflow."""

from __future__ import annotations

from typing import List, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .agents import documentor_node, mitigation_node, risk_node, twin_sync_node
from .models import DocumentationUpdate, DriftItem, MitigationPlan, RiskAssessment


class TwinState(TypedDict, total=False):
    """State schema for the digital twin workflow graph."""
    
    # Populated by TwinSyncAgent
    drift: List[DriftItem]
    
    # Populated by RiskAgent
    risk_assessment: RiskAssessment
    
    # Populated by MitigationAgent
    mitigation_plan: MitigationPlan
    
    # Populated by DocumentorAgent
    documentation_update: DocumentationUpdate


def build_graph():
    """
    Build and compile the LangGraph workflow.
    
    Flow:
        START -> twin_sync -> risk -> mitigation -> documentor -> END
    
    Returns:
        Compiled LangGraph application
    """
    builder = StateGraph(TwinState)
    
    # Add nodes
    builder.add_node("twin_sync", twin_sync_node)
    builder.add_node("risk", risk_node)
    builder.add_node("mitigation", mitigation_node)
    builder.add_node("documentor", documentor_node)
    
    # Define edges (linear flow)
    builder.add_edge(START, "twin_sync")
    builder.add_edge("twin_sync", "risk")
    builder.add_edge("risk", "mitigation")
    builder.add_edge("mitigation", "documentor")
    builder.add_edge("documentor", END)
    
    return builder.compile()


def run_twin_cycle() -> TwinState:
    """
    Execute a complete digital twin assessment cycle.
    
    Returns:
        Final state containing drift, risk assessment,
        mitigation plan, and documentation updates.
    """
    app = build_graph()
    result = app.invoke({})
    return result
