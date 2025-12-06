# src/oscal_dtl/agents/risk.py
"""RiskAgent - Assesses risk severity for configuration drift items."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..config import OPENAI_MODEL
from ..models import DriftItem, RiskAssessment

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
        """You are a cybersecurity risk analyst specializing in NIST 800-53 controls.

Given configuration drifts between intended (OSCAL SSP) and actual system state,
assess each drift item for security risk.

For each item:
- Rate severity as "low", "medium", or "high"
- Provide brief rationale explaining the security impact

Also provide:
- An overall risk score from 0-100 (higher = more risk)
- A summary paragraph of the security posture

Consider factors like:
- Impact on confidentiality, integrity, availability
- Regulatory/compliance implications
- Attack surface exposure
- Data sensitivity"""
    ),
    (
        "human",
        """Drift items detected:

{drift_json}

Return a JSON object with this exact structure:
{{
    "overall_score": <number 0-100>,
    "summary": "<overall security assessment>",
    "items": [
        {{
            "component": "<component name>",
            "attribute": "<attribute name>",
            "severity": "<low|medium|high>",
            "rationale": "<brief explanation>"
        }}
    ]
}}"""
    ),
])


def risk_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assess risk for detected configuration drift.
    
    Uses an LLM to evaluate each drift item and assign severity ratings.
    
    Args:
        state: Graph state containing 'drift' list
        
    Returns:
        Updated state with 'risk_assessment' and enriched 'drift' items
    """
    drift: List[DriftItem] = state.get("drift", [])
    
    if not drift:
        print("⚠️  RiskAgent: No drift items to assess")
        ra = RiskAssessment(
            overall_score=0.0,
            summary="No configuration drift detected. System is compliant with SSP.",
            items=[],
        )
        return {"risk_assessment": ra}
    
    print(f"🔍 RiskAgent: Assessing risk for {len(drift)} drift item(s)...")
    
    # Serialize drift for LLM
    drift_payload = [
        {
            "component": d.component,
            "attribute": d.attribute,
            "expected": d.expected,
            "observed": d.observed,
            "control_ids": d.control_ids,
        }
        for d in drift
    ]
    
    # Invoke LLM
    messages = _PROMPT.format_messages(drift_json=json.dumps(drift_payload, indent=2))
    response = _get_llm().invoke(messages)
    
    # Parse response
    try:
        # Handle potential markdown code blocks in response
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        print("   Warning: Could not parse LLM response, using defaults")
        parsed = {
            "overall_score": 50.0,
            "summary": response.content,
            "items": [],
        }
    
    # Update drift items with severity and rationale
    items_info = parsed.get("items", [])
    for item_info in items_info:
        # Find matching drift item
        for d in drift:
            if d.component == item_info.get("component") and d.attribute == item_info.get("attribute"):
                d.severity = item_info.get("severity")
                d.rationale = item_info.get("rationale")
                break
    
    # Build risk assessment
    ra = RiskAssessment(
        overall_score=float(parsed.get("overall_score", 50.0)),
        summary=parsed.get("summary", ""),
        items=drift,
    )
    
    print(f"   Overall risk score: {ra.overall_score}")
    
    return {"risk_assessment": ra, "drift": drift}
