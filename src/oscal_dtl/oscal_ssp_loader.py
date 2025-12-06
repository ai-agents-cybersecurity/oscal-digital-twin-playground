# src/oscal_dtl/oscal_ssp_loader.py
"""Load and parse OSCAL SSP documents to extract configuration expectations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


def load_ssp(path: str | Path) -> Dict[str, Any]:
    """Load an OSCAL SSP JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_expected_value(value: str) -> str | int | float | bool:
    """Parse a string value into its appropriate type."""
    # Boolean
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    
    # Integer
    try:
        return int(value)
    except ValueError:
        pass
    
    # Float
    try:
        return float(value)
    except ValueError:
        pass
    
    # String
    return value


def extract_expectations(ssp_json: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Extract configuration expectations from OSCAL SSP.
    
    Maps (component_id, attribute) -> {expected: value, controls: [control_ids]}
    
    This implementation looks for custom oscal-dtl:* properties:
      - oscal-dtl:component-id: identifies the component
      - oscal-dtl:attribute: the configuration attribute name
      - oscal-dtl:expected: the expected value
    
    Returns:
        Dict mapping (component_id, attribute) tuples to expectation info
    """
    # Handle both wrapped and unwrapped SSP format
    system = ssp_json.get("system-security-plan", ssp_json)
    impl = system.get("control-implementation", {})
    requirements = impl.get("implemented-requirements", [])
    
    expectations: Dict[Tuple[str, str], Dict[str, Any]] = {}
    
    for req in requirements:
        control_id = req.get("control-id")
        by_components = req.get("by-components", [])
        
        for bc in by_components:
            props = bc.get("props", [])
            
            # Extract oscal-dtl properties
            component_id = None
            attr_name = None
            expected_val: Any = None
            
            for prop in props:
                name = prop.get("name", "")
                value = prop.get("value", "")
                
                if name == "oscal-dtl:component-id":
                    component_id = value
                elif name == "oscal-dtl:attribute":
                    attr_name = value
                elif name == "oscal-dtl:expected":
                    expected_val = _parse_expected_value(value)
            
            # Skip if we don't have required fields
            if not component_id or not attr_name:
                continue
            
            # Build or update expectation entry
            key = (component_id, attr_name)
            if key not in expectations:
                expectations[key] = {
                    "expected": expected_val,
                    "controls": [],
                    "description": bc.get("description", ""),
                }
            
            # Add control ID if not already present
            if control_id and control_id not in expectations[key]["controls"]:
                expectations[key]["controls"].append(control_id)
    
    return expectations


def get_component_map(ssp_json: Dict[str, Any]) -> Dict[str, str]:
    """
    Build a mapping from component UUID to component ID.
    
    Returns:
        Dict mapping component-uuid -> oscal-dtl:component-id
    """
    system = ssp_json.get("system-security-plan", ssp_json)
    impl = system.get("system-implementation", {})
    components = impl.get("components", [])
    
    comp_map = {}
    for comp in components:
        uuid = comp.get("uuid")
        props = comp.get("props", [])
        
        for prop in props:
            if prop.get("name") == "oscal-dtl:component-id":
                comp_map[uuid] = prop.get("value")
                break
    
    return comp_map
