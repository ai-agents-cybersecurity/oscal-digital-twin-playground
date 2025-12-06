#!/usr/bin/env python3
# src/oscal_dtl/cli.py
"""Command-line interface for OSCAL Digital Twin Lab."""

from __future__ import annotations

import argparse
import json
import sys

from .config import validate_config
from .graph import build_graph


def print_section(title: str, char: str = "=") -> None:
    """Print a formatted section header."""
    print(f"\n{char * 3} {title} {char * 3}")


def main() -> int:
    """Run the OSCAL Digital Twin assessment cycle."""
    parser = argparse.ArgumentParser(
        description="OSCAL Digital Twin Lab - Continuous compliance assessment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m oscal_dtl.cli              # Run full assessment cycle
  python -m oscal_dtl.cli --json       # Output results as JSON
  python -m oscal_dtl.cli --verbose    # Show detailed output
        """,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including OSCAL fragments",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip configuration validation",
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not args.skip_validation:
        errors = validate_config()
        if errors:
            print("Configuration errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            print("\nSet OPENAI_API_KEY in .env or environment", file=sys.stderr)
            return 1
    
    print("🚀 OSCAL Digital Twin Lab - Assessment Cycle")
    print("=" * 50)
    
    # Build and run the graph
    app = build_graph()
    result = app.invoke({})
    
    # JSON output mode
    if args.json:
        output = {
            "drift": [
                {
                    "component": d.component,
                    "attribute": d.attribute,
                    "expected": d.expected,
                    "observed": d.observed,
                    "control_ids": d.control_ids,
                    "severity": d.severity,
                    "rationale": d.rationale,
                }
                for d in result.get("drift", [])
            ],
            "risk_assessment": None,
            "mitigation_plan": None,
            "documentation_update": None,
        }
        
        ra = result.get("risk_assessment")
        if ra:
            output["risk_assessment"] = {
                "overall_score": ra.overall_score,
                "summary": ra.summary,
            }
        
        mp = result.get("mitigation_plan")
        if mp:
            output["mitigation_plan"] = {
                "narrative": mp.narrative,
                "by_component": mp.by_component,
            }
        
        du = result.get("documentation_update")
        if du:
            output["documentation_update"] = {
                "assessment_fragment": du.assessment_fragment,
                "poam_fragment": du.poam_fragment,
            }
        
        print(json.dumps(output, indent=2))
        return 0
    
    # Human-readable output
    print_section("Drift Detected")
    drift = result.get("drift", [])
    if drift:
        for d in drift:
            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(d.severity, "⚪")
            print(f"{severity_icon} [{d.severity or 'n/a':6}] {d.component}.{d.attribute}")
            print(f"          Expected: {d.expected}")
            print(f"          Observed: {d.observed}")
            print(f"          Controls: {', '.join(d.control_ids)}")
            if d.rationale:
                print(f"          Rationale: {d.rationale}")
    else:
        print("✅ No drift detected - system is compliant!")
    
    ra = result.get("risk_assessment")
    if ra:
        print_section("Risk Assessment")
        score_bar = "█" * int(ra.overall_score / 10) + "░" * (10 - int(ra.overall_score / 10))
        print(f"Score: {ra.overall_score:.0f}/100 [{score_bar}]")
        print(f"\nSummary:\n{ra.summary}")
    
    mp = result.get("mitigation_plan")
    if mp:
        print_section("Mitigation Plan")
        print(f"\n{mp.narrative}\n")
        if mp.by_component:
            print("Actions by Component:")
            for comp, actions in mp.by_component.items():
                print(f"\n  📦 {comp}:")
                for action in actions:
                    print(f"     • {action}")
    
    du = result.get("documentation_update")
    if du and args.verbose:
        print_section("OSCAL Assessment Fragment (demo)")
        print(json.dumps(du.assessment_fragment, indent=2))
        
        print_section("OSCAL POA&M Fragment (demo)")
        print(json.dumps(du.poam_fragment, indent=2))
    elif du:
        print_section("Documentation")
        print("📄 OSCAL fragments generated (use --verbose to view)")
    
    print("\n" + "=" * 50)
    print("✨ Assessment cycle complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
