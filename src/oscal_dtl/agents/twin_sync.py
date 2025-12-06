# src/oscal_dtl/agents/twin_sync.py
"""TwinSyncAgent - Detects configuration drift between SSP and live config."""

from __future__ import annotations

from typing import Any, Dict

from ..twin_engine import calculate_drift


def twin_sync_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare OSCAL SSP expectations against live configuration.
    
    This node populates the 'drift' key in the graph state with
    a list of DriftItem objects representing configuration mismatches.
    
    Args:
        state: Current graph state
        
    Returns:
        Updated state with 'drift' list populated
    """
    print("🔄 TwinSyncAgent: Comparing SSP expectations vs live config...")
    
    drift = calculate_drift()
    
    if drift:
        print(f"   Found {len(drift)} drift item(s)")
    else:
        print("   No drift detected - system is compliant!")
    
    return {"drift": drift}
