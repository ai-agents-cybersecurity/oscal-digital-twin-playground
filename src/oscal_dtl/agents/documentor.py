# src/oscal_dtl/agents/documentor.py
"""DocumentorAgent - Generates OSCAL-like assessment and POA&M fragments."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..config import OPENAI_API_KEY, OPENAI_MODEL
from ..models import DocumentationUpdate, MitigationPlan, RiskAssessment

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
        """You are an OSCAL documentation expert.

Given a risk assessment and mitigation plan, generate OSCAL-compatible JSON fragments:

1. assessment-results fragment: Documents the findings from this assessment
2. plan-of-action-and-milestones (POA&M) fragment: Documents planned remediation

Use realistic OSCAL structure with:
- UUIDs (can be placeholder format like "uuid-xxx")
- Timestamps
- Proper OSCAL field names (findings, observations, risks, poam-items)
- References to relevant control IDs

Keep the fragments minimal but structurally valid."""
    ),
    (
        "human",
        """Risk Assessment:
Score: {score}
Summary: {summary}

Drift Items:
{items_json}

Mitigation Plan:
{mitigation_json}

Return a JSON object with this exact structure:
{{
    "assessment_fragment": {{
        "assessment-results": {{
            "uuid": "...",
            "metadata": {{}},
            "results": [...]
        }}
    }},
    "poam_fragment": {{
        "plan-of-action-and-milestones": {{
            "uuid": "...",
            "metadata": {{}},
            "poam-items": [...]
        }}
    }}
}}"""
    ),
])


def documentor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate OSCAL-like documentation fragments.
    
    Creates assessment-results and POA&M fragments based on the
    risk assessment and mitigation plan.
    
    Args:
        state: Graph state containing 'risk_assessment' and 'mitigation_plan'
        
    Returns:
        Updated state with 'documentation_update'
    """
    ra: RiskAssessment | None = state.get("risk_assessment")
    mp: MitigationPlan | None = state.get("mitigation_plan")

    if not OPENAI_API_KEY:
        print("⚠️  DocumentorAgent: OPENAI_API_KEY not set, skipping LLM documentation generation")
        return {
            "documentation_update": DocumentationUpdate(
                assessment_fragment={"status": "llm_disabled"},
                poam_fragment={"status": "llm_disabled"},
            )
        }
    
    if ra is None or mp is None:
        print("⚠️  DocumentorAgent: Missing risk assessment or mitigation plan")
        return {}
    
    if not ra.items:
        print("📄 DocumentorAgent: No findings to document")
        du = DocumentationUpdate(
            assessment_fragment={"status": "compliant", "findings": []},
            poam_fragment={"status": "none_required", "poam_items": []},
        )
        return {"documentation_update": du}
    
    print(f"📄 DocumentorAgent: Generating OSCAL fragments...")
    
    # Serialize for LLM
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
    
    mitigation_payload = {
        "narrative": mp.narrative,
        "by_component": mp.by_component,
    }
    
    # Invoke LLM
    messages = _PROMPT.format_messages(
        score=ra.overall_score,
        summary=ra.summary,
        items_json=json.dumps(items_payload, indent=2),
        mitigation_json=json.dumps(mitigation_payload, indent=2),
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
            "assessment_fragment": {"raw_text": response.content},
            "poam_fragment": {"raw_text": response.content},
        }
    
    du = DocumentationUpdate(
        assessment_fragment=parsed.get("assessment_fragment", {}),
        poam_fragment=parsed.get("poam_fragment", {}),
    )
    
    print("   Generated assessment-results and POA&M fragments")
    
    return {"documentation_update": du}
