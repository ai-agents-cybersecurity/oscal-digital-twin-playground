#!/usr/bin/env python3
# src/oscal_dtl/scenario_runner.py
"""Scenario runner for what-if configuration testing."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import LIVE_CONFIG_PATH, validate_config
from .graph import build_graph
from .models import DriftItem
from .twin_engine import calculate_drift, load_live_state


def load_scenario(scenario_path: Path) -> Dict[str, Any]:
    """Load a scenario definition file."""
    with open(scenario_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_scenario(base_config: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply scenario modifications to a base configuration.
    
    Scenario format:
    ```yaml
    name: "Scenario Name"
    description: "What this scenario tests"
    changes:
      - component: web-app
        attribute: mfa_enabled
        value: false
      - component: database
        attribute: encrypted_at_rest
        value: true
    ```
    """
    config = copy.deepcopy(base_config)
    
    for change in scenario.get("changes", []):
        comp = change.get("component")
        attr = change.get("attribute")
        value = change.get("value")
        
        if comp and attr is not None:
            if comp not in config.get("components", {}):
                config.setdefault("components", {})[comp] = {}
            config["components"][comp][attr] = value
    
    return config


def run_scenario(
    scenario_path: Path,
    base_config_path: Optional[Path] = None,
    run_full_pipeline: bool = False,
) -> Dict[str, Any]:
    """
    Run a scenario and return results.
    
    Args:
        scenario_path: Path to scenario YAML file
        base_config_path: Base config to modify (default: LIVE_CONFIG_PATH)
        run_full_pipeline: If True, run full LLM pipeline; otherwise just drift detection
    
    Returns:
        Dict with scenario info, modified config, and drift results
    """
    base_config_path = base_config_path or LIVE_CONFIG_PATH
    
    # Load base config
    with open(base_config_path, "r", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)
    
    # Load and apply scenario
    scenario = load_scenario(scenario_path)
    modified_config = apply_scenario(base_config, scenario)
    
    # Write modified config to temp file for drift calculation
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        yaml.dump(modified_config, tmp)
        tmp_path = Path(tmp.name)
    
    try:
        # Calculate drift with modified config
        drift = calculate_drift(live_path=tmp_path)
        
        results = {
            "scenario": {
                "name": scenario.get("name", scenario_path.stem),
                "description": scenario.get("description", ""),
                "changes": scenario.get("changes", []),
            },
            "modified_config": modified_config,
            "drift": drift,
            "drift_count": len(drift),
        }
        
        # Optionally run full pipeline
        if run_full_pipeline:
            # Temporarily swap live config path
            from . import config as cfg
            original_path = cfg.LIVE_CONFIG_PATH
            cfg.LIVE_CONFIG_PATH = tmp_path
            
            try:
                app = build_graph()
                pipeline_result = app.invoke({})
                results["risk_assessment"] = pipeline_result.get("risk_assessment")
                results["mitigation_plan"] = pipeline_result.get("mitigation_plan")
                results["documentation_update"] = pipeline_result.get("documentation_update")
            finally:
                cfg.LIVE_CONFIG_PATH = original_path
        
        return results
    
    finally:
        # Cleanup temp file
        tmp_path.unlink(missing_ok=True)


def compare_scenarios(
    scenario_paths: List[Path],
    base_config_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Run multiple scenarios and compare their drift results.
    
    Returns:
        List of scenario results for comparison
    """
    results = []
    for path in scenario_paths:
        result = run_scenario(path, base_config_path, run_full_pipeline=False)
        results.append(result)
    return results


def print_scenario_result(result: Dict[str, Any], verbose: bool = False) -> None:
    """Print scenario results in human-readable format."""
    scenario = result["scenario"]
    
    print(f"\n{'='*60}")
    print(f"📋 Scenario: {scenario['name']}")
    print(f"{'='*60}")
    
    if scenario["description"]:
        print(f"\n{scenario['description']}")
    
    print("\n📝 Changes Applied:")
    for change in scenario["changes"]:
        print(f"   • {change['component']}.{change['attribute']} = {change['value']}")
    
    print(f"\n🔍 Drift Analysis ({result['drift_count']} items):")
    
    if result["drift"]:
        for d in result["drift"]:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(d.severity, "⚪")
            print(f"   {severity_icon} {d.component}.{d.attribute}")
            print(f"      Expected: {d.expected} | Observed: {d.observed}")
            print(f"      Controls: {', '.join(d.control_ids)}")
    else:
        print("   ✅ No drift - fully compliant!")
    
    # Risk assessment if available
    ra = result.get("risk_assessment")
    if ra:
        print(f"\n📊 Risk Score: {ra.overall_score:.0f}/100")
        print(f"   {ra.summary[:200]}..." if len(ra.summary) > 200 else f"   {ra.summary}")
    
    # Mitigation if available
    mp = result.get("mitigation_plan")
    if mp and verbose:
        print(f"\n🛠️  Mitigation Plan:")
        print(f"   {mp.narrative[:300]}..." if len(mp.narrative) > 300 else f"   {mp.narrative}")


def main() -> int:
    """CLI for scenario runner."""
    parser = argparse.ArgumentParser(
        description="OSCAL Digital Twin - Scenario Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m oscal_dtl.scenario_runner scenarios/mfa_disabled.yaml
  python -m oscal_dtl.scenario_runner scenarios/*.yaml --compare
  python -m oscal_dtl.scenario_runner scenarios/compliant.yaml --full
        """,
    )
    parser.add_argument(
        "scenarios",
        nargs="+",
        type=Path,
        help="Path(s) to scenario YAML file(s)",
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        help="Base configuration file (default: live-config-1.yaml)",
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="Run full LLM pipeline (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare multiple scenarios side-by-side",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    # Validate config if running full pipeline
    if args.full:
        errors = validate_config()
        if errors:
            print("Configuration errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
    
    print("🎯 OSCAL Digital Twin - Scenario Runner")
    print("=" * 60)
    
    # Expand glob patterns
    scenario_paths = []
    for p in args.scenarios:
        if "*" in str(p):
            scenario_paths.extend(p.parent.glob(p.name))
        else:
            scenario_paths.append(p)
    
    # Validate paths
    for p in scenario_paths:
        if not p.exists():
            print(f"Error: Scenario not found: {p}", file=sys.stderr)
            return 1
    
    # Run scenarios
    results = []
    for path in scenario_paths:
        print(f"\n⏳ Running scenario: {path.name}...")
        result = run_scenario(path, args.base_config, args.full)
        results.append(result)
        
        if not args.json and not args.compare:
            print_scenario_result(result, args.verbose)
    
    # Compare mode
    if args.compare and len(results) > 1:
        print(f"\n{'='*60}")
        print("📊 Scenario Comparison")
        print(f"{'='*60}")
        print(f"\n{'Scenario':<30} {'Drift Items':<15} {'Status'}")
        print("-" * 60)
        for r in results:
            name = r["scenario"]["name"][:28]
            count = r["drift_count"]
            status = "✅ Compliant" if count == 0 else f"⚠️  {count} issues"
            print(f"{name:<30} {count:<15} {status}")
    
    # JSON output
    if args.json:
        import json
        output = []
        for r in results:
            out = {
                "scenario": r["scenario"],
                "drift_count": r["drift_count"],
                "drift": [
                    {
                        "component": d.component,
                        "attribute": d.attribute,
                        "expected": d.expected,
                        "observed": d.observed,
                        "control_ids": d.control_ids,
                        "severity": d.severity,
                    }
                    for d in r["drift"]
                ],
            }
            if r.get("risk_assessment"):
                ra = r["risk_assessment"]
                out["risk_score"] = ra.overall_score
            output.append(out)
        print(json.dumps(output, indent=2))
    
    print(f"\n✨ Completed {len(results)} scenario(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
