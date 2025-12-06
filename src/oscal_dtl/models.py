# src/oscal_dtl/models.py
"""Pydantic models for OSCAL Digital Twin Lab."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ComponentConfig(BaseModel):
    """Configuration for a single system component."""
    
    name: str
    attributes: Dict[str, str | int | float | bool]


class LiveState(BaseModel):
    """Represents the actual/observed state of the system."""
    
    system_id: str
    components: Dict[str, ComponentConfig]


class DriftItem(BaseModel):
    """A single configuration drift between expected and observed state."""
    
    component: str
    attribute: str
    expected: str | int | float | bool | None
    observed: str | int | float | bool | None
    control_ids: List[str] = Field(default_factory=list)
    severity: Optional[Literal["low", "medium", "high"]] = None
    rationale: Optional[str] = None

    def __str__(self) -> str:
        sev = self.severity or "n/a"
        return (
            f"[{sev}] {self.component}.{self.attribute}: "
            f"expected={self.expected} observed={self.observed} "
            f"controls={self.control_ids}"
        )


class RiskAssessment(BaseModel):
    """Risk assessment result from the RiskAgent."""
    
    overall_score: float = Field(ge=0, le=100, description="Risk score 0-100")
    summary: str
    items: List[DriftItem] = Field(default_factory=list)


class MitigationPlan(BaseModel):
    """Mitigation plan from the MitigationAgent."""
    
    narrative: str
    by_component: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Component -> list of remediation actions"
    )


class DocumentationUpdate(BaseModel):
    """OSCAL-like documentation fragments from the DocumentorAgent."""
    
    assessment_fragment: Dict[str, Any] = Field(default_factory=dict)
    poam_fragment: Dict[str, Any] = Field(default_factory=dict)


class Expectation(BaseModel):
    """An expected configuration value derived from OSCAL SSP."""
    
    component_id: str
    attribute: str
    expected_value: str | int | float | bool | None
    control_ids: List[str] = Field(default_factory=list)
    description: Optional[str] = None
