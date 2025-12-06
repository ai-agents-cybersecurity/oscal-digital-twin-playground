# src/oscal_dtl/agents/mitigation.py
"""MitigationAgent - Proposes remediation steps for configuration drift."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..config import OPENAI_MODEL
from ..models import MitigationPlan, RiskAssessment

# Lazy initialization to avoid import-time API key validation
_llm: Optional[ChatOpenAI] = None


def _get_llm() -> ChatOpenAI:
    """Get or create the LLM instance."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)
    return _llm

_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a security engineer providing actionable remediation guidance.

Given a risk assessment with configuration drift items, propose concrete
mitigation steps to bring the system back into compliance with its OSCAL SSP.

Your recommendations should be:
- Specific and actionable
- Prioritized by severity
- Grouped by component
- Include both immediate fixes and longer-term improvements"""
    ),
    (
        "human",
        """Risk Assessment:

Overall Score: {score}
Summary: {summary}

Drift Items:
{items_json}

Return a JSON object with this exact structure:
{{
    "narrative": "<executive summary of remediation plan>",
    "by_component": {{
        "<component_name>": [
            "<action 1>",
            "<action 2>"
        ]
    }}
}}"""
    ),
])


def mitigation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate mitigation plan for identified risks.
    
    Uses an LLM to propose concrete remediation steps grouped by component.
    
    Args:
        state: Graph state containing 'risk_assessment'
        
    Returns:
        Updated state with 'mitigation_plan'
    """
    ra: RiskAssessment | None = state.get("risk_assessment")
    
    if ra is None:
        print("⚠️  MitigationAgent: No risk assessment available")
        return {}
    
    if not ra.items:
        print("✅ MitigationAgent: No drift items - no mitigation needed")
        mp = MitigationPlan(
            narrative="No remediation required. System is compliant.",
            by_component={},
        )
        return {"mitigation_plan": mp}
    
    print(f"🛠️  MitigationAgent: Generating remediation plan...")
    
    # Serialize items for LLM
    items_payload = [
        {
            "component": d.component,
            "attribute": d.attribute,
            "expected": d.expected,
            "observed": d.observed,
            "control_ids": d.control_ids,
            "severity": d.severity,
            "rationale": d.rationale,
        }
        for d in ra.items
    ]
    
    # Invoke LLM
    messages = _PROMPT.format_messages(
        score=ra.overall_score,
        summary=ra.summary,
        items_json=json.dumps(items_payload, indent=2),
    )
    response = _get_llm().invoke(messages)
    
    # Parse response
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        print("   Warning: Could not parse LLM response")
        parsed = {
            "narrative": response.content,
            "by_component": {},
        }
    
    mp = MitigationPlan(
        narrative=parsed.get("narrative", ""),
        by_component=parsed.get("by_component", {}),
    )
    
    print(f"   Generated plan for {len(mp.by_component)} component(s)")
    
    return {"mitigation_plan": mp}
