#!/usr/bin/env python3
# src/oscal_dtl/app.py
"""Streamlit UI for OSCAL Digital Twin Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import yaml

from oscal_dtl.config import BASE_DIR, DEMO_SSP_PATH, LIVE_CONFIG_PATH, validate_config
from oscal_dtl.models import DriftItem
from oscal_dtl.oscal_ssp_loader import extract_expectations, load_ssp
from oscal_dtl.twin_engine import calculate_drift, load_live_state

# Page config
st.set_page_config(
    page_title="OSCAL Digital Twin Lab",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .drift-high { background-color: #ffcccc; padding: 10px; border-radius: 5px; margin: 5px 0; color: #000000; }
    .drift-medium { background-color: #fff3cd; padding: 10px; border-radius: 5px; margin: 5px 0; color: #000000; }
    .drift-low { background-color: #d4edda; padding: 10px; border-radius: 5px; margin: 5px 0; color: #000000; }
    .drift-none { background-color: #e7e7e7; padding: 10px; border-radius: 5px; margin: 5px 0; color: #000000; }
    .metric-card { 
        background-color: #f0f2f6; 
        padding: 20px; 
        border-radius: 10px; 
        text-align: center;
        margin: 10px 0;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
</style>
""", unsafe_allow_html=True)


def load_live_config_raw() -> Dict[str, Any]:
    """Load raw live config as dict."""
    with open(LIVE_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_scenarios() -> Dict[str, Path]:
    """Get available scenario files."""
    scenarios_dir = BASE_DIR / "data" / "scenarios"
    if not scenarios_dir.exists():
        return {}
    return {p.stem: p for p in scenarios_dir.glob("*.yaml")}


def apply_config_changes(base: Dict, changes: Dict[str, Dict[str, Any]]) -> Dict:
    """Apply UI changes to config."""
    import copy
    config = copy.deepcopy(base)
    for comp, attrs in changes.items():
        if comp not in config.get("components", {}):
            config.setdefault("components", {})[comp] = {}
        config["components"][comp].update(attrs)
    return config


def render_drift_card(drift: DriftItem) -> None:
    """Render a drift item as a styled card."""
    severity = drift.severity or "none"
    css_class = f"drift-{severity}"
    icon = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "⚪"}.get(severity, "⚪")
    
    st.markdown(f"""
    <div class="{css_class}">
        <strong>{icon} {drift.component}.{drift.attribute}</strong><br>
        <small>Expected: <code>{drift.expected}</code> | Observed: <code>{drift.observed}</code></small><br>
        <small>Controls: {', '.join(drift.control_ids)}</small>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar() -> Dict[str, Dict[str, Any]]:
    """Render sidebar with config controls."""
    st.sidebar.title("🔧 Configuration Controls")
    
    # Load base config
    base_config = load_live_config_raw()
    changes: Dict[str, Dict[str, Any]] = {}
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Toggle Live Config")
    
    # Extract expectations for reference
    ssp = load_ssp(DEMO_SSP_PATH)
    expectations = extract_expectations(ssp)
    expected_map = {(k[0], k[1]): v["expected"] for k, v in expectations.items()}
    
    for comp_name, comp_config in base_config.get("components", {}).items():
        with st.sidebar.expander(f"📦 {comp_name}", expanded=True):
            comp_changes = {}
            for attr, value in comp_config.items():
                expected = expected_map.get((comp_name, attr))
                
                # Show indicator if this attribute has SSP expectation
                if expected is not None:
                    is_compliant = value == expected
                    indicator = "✅" if is_compliant else "⚠️"
                    label = f"{indicator} {attr}"
                    help_text = f"SSP expects: {expected}"
                else:
                    label = f"   {attr}"
                    help_text = "No SSP requirement"
                
                # Render appropriate input based on type
                if isinstance(value, bool):
                    new_val = st.checkbox(label, value=value, key=f"{comp_name}_{attr}", help=help_text)
                elif isinstance(value, int):
                    new_val = st.number_input(label, value=value, key=f"{comp_name}_{attr}", help=help_text)
                elif isinstance(value, str):
                    new_val = st.text_input(label, value=value, key=f"{comp_name}_{attr}", help=help_text)
                else:
                    new_val = value
                
                if new_val != value:
                    comp_changes[attr] = new_val
            
            if comp_changes:
                changes[comp_name] = comp_changes
    
    # Scenario loader
    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Load Scenario")
    scenarios = get_scenarios()
    if scenarios:
        scenario_name = st.sidebar.selectbox(
            "Select scenario",
            ["(current config)"] + list(scenarios.keys()),
            key="scenario_select"
        )
        if scenario_name != "(current config)" and st.sidebar.button("Apply Scenario"):
            with open(scenarios[scenario_name], "r") as f:
                scenario = yaml.safe_load(f)
            for change in scenario.get("changes", []):
                comp = change.get("component")
                attr = change.get("attribute")
                val = change.get("value")
                if comp and attr is not None:
                    changes.setdefault(comp, {})[attr] = val
            st.sidebar.success(f"Applied: {scenario.get('name', scenario_name)}")
            st.rerun()
    
    return changes


def render_main_dashboard(drift: List[DriftItem], config: Dict) -> None:
    """Render main dashboard content."""
    st.title("🔐 OSCAL Digital Twin Lab")
    st.markdown("*Real-time compliance drift detection between OSCAL SSP and live configuration*")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    total_drift = len(drift)
    high_count = sum(1 for d in drift if d.severity == "high")
    medium_count = sum(1 for d in drift if d.severity == "medium")
    low_count = sum(1 for d in drift if d.severity == "low")
    
    with col1:
        st.metric("Total Drift Items", total_drift, delta=None)
    with col2:
        st.metric("🔴 High Severity", high_count)
    with col3:
        st.metric("🟡 Medium Severity", medium_count)
    with col4:
        st.metric("🟢 Low Severity", low_count)
    
    # Status banner
    if total_drift == 0:
        st.success("✅ **System is fully compliant!** No drift detected between SSP and live configuration.")
    elif high_count > 0:
        st.error(f"🚨 **Critical drift detected!** {high_count} high-severity issue(s) require immediate attention.")
    elif medium_count > 0:
        st.warning(f"⚠️ **Configuration drift detected.** {medium_count} medium-severity issue(s) found.")
    else:
        st.info(f"ℹ️ **Minor drift detected.** {low_count} low-severity issue(s) found.")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Drift Analysis", "📋 Live Config", "📜 SSP Summary", "🔄 Run Pipeline"])
    
    with tab1:
        render_drift_tab(drift)
    
    with tab2:
        render_config_tab(config)
    
    with tab3:
        render_ssp_tab()
    
    with tab4:
        render_pipeline_tab(drift)


def render_drift_tab(drift: List[DriftItem]) -> None:
    """Render drift analysis tab."""
    st.subheader("Configuration Drift Details")
    
    if not drift:
        st.info("No drift items to display. System is compliant!")
        return
    
    # Group by severity
    by_severity = {"high": [], "medium": [], "low": [], None: []}
    for d in drift:
        by_severity[d.severity].append(d)
    
    # Display by severity
    for severity in ["high", "medium", "low", None]:
        items = by_severity[severity]
        if items:
            severity_label = severity.upper() if severity else "UNASSESSED"
            st.markdown(f"### {severity_label} ({len(items)})")
            for d in items:
                render_drift_card(d)


def render_config_tab(config: Dict) -> None:
    """Render live config tab."""
    st.subheader("Current Live Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**YAML View**")
        st.code(yaml.dump(config, default_flow_style=False), language="yaml")
    
    with col2:
        st.markdown("**JSON View**")
        st.json(config)


def render_ssp_tab() -> None:
    """Render SSP summary tab."""
    st.subheader("OSCAL SSP Expectations")
    
    ssp = load_ssp(DEMO_SSP_PATH)
    expectations = extract_expectations(ssp)
    
    st.markdown(f"**{len(expectations)}** configuration expectations defined in SSP")
    
    # Table view
    data = []
    for (comp, attr), info in expectations.items():
        data.append({
            "Component": comp,
            "Attribute": attr,
            "Expected": info["expected"],
            "Controls": ", ".join(info["controls"]),
        })
    
    if data:
        st.dataframe(data, use_container_width=True)
    
    # Raw SSP viewer
    with st.expander("View Raw SSP JSON"):
        st.json(ssp)


def render_pipeline_tab(drift: List[DriftItem]) -> None:
    """Render LLM pipeline tab."""
    st.subheader("🤖 Run Full Assessment Pipeline")
    
    # Check for API key
    errors = validate_config()
    api_key_missing = any("OPENAI_API_KEY" in e for e in errors)
    
    if api_key_missing:
        st.warning("⚠️ OPENAI_API_KEY not set. Full pipeline requires an API key.")
        st.code("export OPENAI_API_KEY=sk-your-key-here", language="bash")
        return
    
    if not drift:
        st.info("No drift detected - pipeline analysis not needed.")
        return
    
    st.markdown("""
    The full pipeline will:
    1. **TwinSyncAgent** - Detect drift (already done)
    2. **RiskAgent** - Assess severity and impact
    3. **MitigationAgent** - Generate remediation steps
    4. **DocumentorAgent** - Create OSCAL fragments
    """)
    
    if st.button("🚀 Run Full Pipeline", type="primary"):
        with st.spinner("Running LLM pipeline..."):
            try:
                from oscal_dtl.graph import build_graph
                app = build_graph()
                result = app.invoke({})
                
                st.success("Pipeline completed!")
                
                # Risk Assessment
                ra = result.get("risk_assessment")
                if ra:
                    st.markdown("### 📊 Risk Assessment")
                    st.metric("Risk Score", f"{ra.overall_score:.0f}/100")
                    st.markdown(ra.summary)
                
                # Mitigation Plan
                mp = result.get("mitigation_plan")
                if mp:
                    st.markdown("### 🛠️ Mitigation Plan")
                    st.markdown(mp.narrative)
                    for comp, actions in mp.by_component.items():
                        with st.expander(f"📦 {comp}"):
                            for action in actions:
                                st.markdown(f"• {action}")
                
                # Documentation
                du = result.get("documentation_update")
                if du:
                    st.markdown("### 📄 OSCAL Fragments")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Assessment Results**")
                        st.json(du.assessment_fragment)
                    with col2:
                        st.markdown("**POA&M**")
                        st.json(du.poam_fragment)
            
            except Exception as e:
                st.error(f"Pipeline error: {e}")


def main():
    """Main Streamlit app entry point."""
    # Sidebar controls
    changes = render_sidebar()
    
    # Apply changes to config
    base_config = load_live_config_raw()
    current_config = apply_config_changes(base_config, changes)
    
    # Calculate drift with modified config
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        yaml.dump(current_config, tmp)
        tmp_path = Path(tmp.name)
    
    try:
        drift = calculate_drift(live_path=tmp_path)
        
        # Simple severity assignment for display (without LLM)
        for d in drift:
            # Heuristic severity based on control IDs
            if any(c.startswith("IA-2") or c.startswith("SC-28") for c in d.control_ids):
                d.severity = "high"
            elif any(c.startswith("SC-") or c.startswith("IA-5") for c in d.control_ids):
                d.severity = "medium"
            else:
                d.severity = "low"
        
        render_main_dashboard(drift, current_config)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
