# src/oscal_dtl/twin_engine.py
"""Core drift detection engine comparing OSCAL SSP expectations vs live config."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml

from .config import DEMO_SSP_PATH, LIVE_CONFIG_PATH
from .models import ComponentConfig, DriftItem, LiveState
from .oscal_ssp_loader import extract_expectations, load_ssp


def load_live_state(path: str | Path) -> LiveState:
    """Load live system state from a YAML configuration file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    components = {}
    for name, cfg in data.get("components", {}).items():
        components[name] = ComponentConfig(name=name, attributes=cfg)
    
    return LiveState(
        system_id=data.get("system_id", "unknown"),
        components=components,
    )


def calculate_drift(
    ssp_path: Optional[str | Path] = None,
    live_path: Optional[str | Path] = None,
) -> List[DriftItem]:
    """
    Calculate configuration drift between SSP expectations and live config.
    
    Args:
        ssp_path: Path to OSCAL SSP JSON (default: DEMO_SSP_PATH)
        live_path: Path to live config YAML (default: LIVE_CONFIG_PATH)
    
    Returns:
        List of DriftItem objects representing mismatches
    """
    ssp_path = ssp_path or DEMO_SSP_PATH
    live_path = live_path or LIVE_CONFIG_PATH
    
    # Load and parse SSP expectations
    ssp = load_ssp(ssp_path)
    expectations = extract_expectations(ssp)
    
    # Load live configuration
    live = load_live_state(live_path)
    
    drift_items: List[DriftItem] = []
    
    # Compare each expectation against live config
    for (comp_id, attr), info in expectations.items():
        expected = info.get("expected")
        controls = info.get("controls", [])
        
        # Get observed value from live config
        comp_cfg = live.components.get(comp_id)
        observed = None
        if comp_cfg:
            observed = comp_cfg.attributes.get(attr)
        
        # Check for drift
        if observed != expected:
            drift_items.append(
                DriftItem(
                    component=comp_id,
                    attribute=attr,
                    expected=expected,
                    observed=observed,
                    control_ids=controls,
                )
            )
    
    return drift_items


def get_live_state_summary(path: Optional[str | Path] = None) -> str:
    """Get a human-readable summary of the live state."""
    path = path or LIVE_CONFIG_PATH
    live = load_live_state(path)
    
    lines = [f"System: {live.system_id}", "Components:"]
    for name, comp in live.components.items():
        lines.append(f"  {name}:")
        for attr, val in comp.attributes.items():
            lines.append(f"    {attr}: {val}")
    
    return "\n".join(lines)
