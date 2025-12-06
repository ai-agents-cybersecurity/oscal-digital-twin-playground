Let’s build the **OSCAL Digital Twin Playground** as a separate-but-friends-with `oscal-agent-lab` (I addded the folder to the workspace for visibility).

Below is a **concrete repo design + starter code** you can drop straight into a new project.

---

## 1. Concept: `oscal-digital-twin-lab`

**One-liner:**

> A small, simulated environment where an OSCAL‑backed “digital twin” of a system is continuously compared against a “live config” by LangGraph agents to detect drift, assess risk, and propose remediations.

You’ll use:

* Real **OSCAL examples** from `usnistgov/oscal-content` (SSPs, catalogs, etc.) ([GitHub][1])
* The NIST CSWP 53 twin/agent vision as inspiration (OSCAL SSP = “DNA” of the digital twin; AI agents reason over it). ([NIST Computer Security Resource Center][2])
* **LangGraph** for multi‑agent orchestration ([LangChain Docs][3])
* **LangChain** for LLM + retrieval.

### Core loop (what your project “does”)

1. **OSCAL Twin**

   * An OSCAL SSP (System Security Plan) = your **declared / intended** system state.
2. **Live Config**

   * A simple JSON/YAML describing the **actual** state of a tiny system (e.g. MFA on/off, logging enabled, storage encrypted, etc.).
3. **Agents**:

   * **TwinSyncAgent** – compares SSP vs live config → identifies **drift**.
   * **RiskAgent** – maps drift → affected controls & rough risk score.
   * **MitigationAgent** – proposes remediation steps (human-readable and optionally pseudo-config).
   * **DocumentorAgent** – writes an updated OSCAL-ish assessment/POA&M fragment documenting the issue.

You run a “cycle”, watch the agents reason, and see the twin updated. It’s a **toy version** of what NIST describes in CSWP 53: continuous, agentic, digital-twin-based assurance. ([NIST Computer Security Resource Center][2])

---

## 2. Repo skeleton

```text
oscal-digital-twin-lab/
  README.md
  pyproject.toml          # or requirements.txt
  .env.example
  data/
    oscal-content/        # git submodule: usnistgov/oscal-content
    ssp/
      demo-ssp.json       # small OSCAL SSP (from examples or handcrafted)
    live_state/
      live-config-1.yaml  # our mock “actual system state”
  src/
    oscal_dtl/
      __init__.py
      config.py
      models.py           # Pydantic models for LiveState, DriftItem, etc.
      oscal_ssp_loader.py # load & flatten SSP into internal representation
      twin_engine.py      # compare SSP vs live config, produce drift
      agents/
        __init__.py
        twin_sync.py
        risk.py
        mitigation.py
        documentor.py
      graph.py            # LangGraph wiring
      cli.py              # simple scenario runner
```

---

## 3. Data model: tiny “system twin”

Let’s keep the **live config** deliberately simple. Example `data/live_state/live-config-1.yaml`:

```yaml
system_id: demo-webapp
components:
  web-app:
    mfa_enabled: false
    logging_enabled: true
    tls_version: "TLS1.0"
  database:
    encrypted_at_rest: false
    backup_frequency_hours: 48
  idp:
    mfa_enabled: true
    password_min_length: 8
```

Your **OSCAL SSP** (JSON) will describe intended implementations for controls like AC‑2, IA‑2, AU‑2, SC‑13, etc. from the NIST OSCAL examples. ([GitHub][1])

We’ll map:

* **OSCAL control implementations → simple expectations** (e.g. “MFA required for admin access”).
* **Live config → observed values**.
* **Drift** = expectation vs observation mismatch.

---

## 4. Basic code scaffolding

### 4.1 `config.py`

```python
# src/oscal_dtl/config.py
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]

OSCAL_CONTENT_DIR = BASE_DIR / "data" / "oscal-content"

# Pick or create a small SSP
DEMO_SSP_PATH = BASE_DIR / "data" / "ssp" / "demo-ssp.json"

LIVE_CONFIG_PATH = BASE_DIR / "data" / "live_state" / "live-config-1.yaml"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
```

### 4.2 `models.py` – state of the world

```python
# src/oscal_dtl/models.py
from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel

class ComponentConfig(BaseModel):
    name: str
    attributes: Dict[str, str | int | float | bool]

class LiveState(BaseModel):
    system_id: str
    components: Dict[str, ComponentConfig]

class DriftItem(BaseModel):
    component: str
    attribute: str
    expected: str | int | float | bool | None
    observed: str | int | float | bool | None
    control_ids: List[str]  # relevant OSCAL controls (e.g., ["AC-2", "IA-2"])
    severity: Optional[Literal["low", "medium", "high"]] = None
    rationale: Optional[str] = None

class RiskAssessment(BaseModel):
    overall_score: float
    summary: str
    items: List[DriftItem]

class MitigationPlan(BaseModel):
    narrative: str
    by_component: Dict[str, List[str]]  # component -> list of suggested actions

class DocumentationUpdate(BaseModel):
    assessment_fragment: Dict
    poam_fragment: Dict
```

### 4.3 `oscal_ssp_loader.py` – brutally pragmatic loader

We’ll assume an OSCAL SSP similar to NIST examples (implementation statements per control). ([GitHub][1])

```python
# src/oscal_dtl/oscal_ssp_loader.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

def load_ssp(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_expectations(ssp_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Map (component, attribute) -> expected_value + associated controls.

    For v0, we keep this very simple and rely on a convention:
      - implementation statements mention simple key=value statements
      - metadata 'oscal-dtl:attribute' & 'oscal-dtl:component' can be used
        to tag which live config attribute this statement corresponds to.

    Return dict like:
      {
        ("web-app", "mfa_enabled"): {
            "expected": True,
            "controls": ["IA-2", "IA-2(1)"],
        },
        ...
      }
    """
    system = ssp_json.get("system-security-plan", ssp_json)
    impl = system.get("control-implementation", {})
    statements = impl.get("implemented-requirements", [])

    expectations: Dict[tuple, Dict[str, Any]] = {}

    for req in statements:
        control_id = req.get("control-id")
        by_components = req.get("by-components", [])
        for bc in by_components:
            comp_id = bc.get("component-uuid") or bc.get("component-id")
            # For demo purposes, assume props like:
            # { "name": "oscal-dtl:attribute", "value": "mfa_enabled" }
            # { "name": "oscal-dtl:expected", "value": "true" }
            props = bc.get("props", [])
            attr_name = None
            expected_val: Any = None
            for p in props:
                name = p.get("name")
                value = p.get("value")
                if name == "oscal-dtl:attribute":
                    attr_name = value
                elif name == "oscal-dtl:expected":
                    # naive parse
                    if value in {"true", "false"}:
                        expected_val = value == "true"
                    else:
                        try:
                            expected_val = int(value)
                        except ValueError:
                            expected_val = value

            if not attr_name:
                continue

            key = (comp_id, attr_name)
            entry = expectations.setdefault(key, {"expected": expected_val, "controls": []})
            if control_id and control_id not in entry["controls"]:
                entry["controls"].append(control_id)

    return expectations
```

> You can either:
>
> * embed these `oscal-dtl:*` props into your own demo SSP, or
> * later get fancier and use the text of implementation statements + an LLM to infer mappings.

### 4.4 `twin_engine.py` – compute drift

```python
# src/oscal_dtl/twin_engine.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Any, List

import yaml

from .config import DEMO_SSP_PATH, LIVE_CONFIG_PATH
from .models import LiveState, ComponentConfig, DriftItem
from .oscal_ssp_loader import load_ssp, extract_expectations

def load_live_state(path: str | Path) -> LiveState:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    comps = {}
    for name, cfg in data.get("components", {}).items():
        comps[name] = ComponentConfig(name=name, attributes=cfg)

    return LiveState(system_id=data.get("system_id", "unknown"), components=comps)

def calculate_drift() -> List[DriftItem]:
    """
    Load SSP + live config, compute mismatches.
    """
    ssp = load_ssp(DEMO_SSP_PATH)
    expectations_raw = extract_expectations(ssp)
    live = load_live_state(LIVE_CONFIG_PATH)

    drift_items: List[DriftItem] = []

    for (comp_id, attr), info in expectations_raw.items():
        expected = info.get("expected")
        controls = info.get("controls", [])

        comp_cfg = live.components.get(comp_id)
        observed = None
        if comp_cfg:
            observed = comp_cfg.attributes.get(attr)

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
```

---

## 5. LangGraph: agents & graph

We’ll define a simple **state schema** for the graph and four nodes.

### 5.1 Graph state

```python
# src/oscal_dtl/graph.py
from __future__ import annotations

from typing_extensions import TypedDict
from typing import List, Optional

from langgraph.graph import StateGraph, START, END

from .models import DriftItem, RiskAssessment, MitigationPlan, DocumentationUpdate
from .agents.twin_sync import twin_sync_node
from .agents.risk import risk_node
from .agents.mitigation import mitigation_node
from .agents.documentor import documentor_node

class TwinState(TypedDict, total=False):
    drift: List[DriftItem]
    risk_assessment: RiskAssessment
    mitigation_plan: MitigationPlan
    documentation_update: DocumentationUpdate

def build_graph():
    builder = StateGraph(TwinState)

    builder.add_node("twin_sync", twin_sync_node)
    builder.add_node("risk", risk_node)
    builder.add_node("mitigation", mitigation_node)
    builder.add_node("documentor", documentor_node)

    builder.add_edge(START, "twin_sync")
    builder.add_edge("twin_sync", "risk")
    builder.add_edge("risk", "mitigation")
    builder.add_edge("mitigation", "documentor")
    builder.add_edge("documentor", END)

    return builder.compile()
```

### 5.2 TwinSyncAgent

```python
# src/oscal_dtl/agents/twin_sync.py
from __future__ import annotations

from typing import Dict, Any

from ..twin_engine import calculate_drift

def twin_sync_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare SSP + live config, populate drift list.
    """
    drift = calculate_drift()
    return {"drift": drift}
```

### 5.3 RiskAgent

Uses the LLM to rank severity & summarize.

```python
# src/oscal_dtl/agents/risk.py
from __future__ import annotations

from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import OPENAI_MODEL
from ..models import DriftItem, RiskAssessment

_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a cybersecurity risk analyst. "
            "Given configuration drifts and their related OSCAL/NIST controls, "
            "rate each as low/medium/high severity and produce an overall summary "
            "and score between 0 and 100 (higher = more risk)."
        ),
        (
            "human",
            "Drift items:\n\n{drift_json}\n\n"
            "Return JSON with fields: 'overall_score', 'summary', and "
            "for each item its 'severity' and 'rationale'."
        ),
    ]
)

def risk_node(state: Dict[str, Any]) -> Dict[str, Any]:
    drift: List[DriftItem] = state.get("drift", [])
    if not drift:
        ra = RiskAssessment(overall_score=0.0, summary="No drift detected.", items=[])
        return {"risk_assessment": ra}

    # Serialize drift to JSON-ish structure for the prompt
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

    msg = _PROMPT.format(drift_json=drift_payload)
    resp = _llm.invoke(msg.to_messages())

    # Very simple parsing (you can harden this later)
    import json
    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {"overall_score": 50.0, "summary": resp.content, "items": []}

    # Update severity/rationale back onto DriftItems
    items_map = parsed.get("items", [])
    for i, item_info in enumerate(items_map):
        if i < len(drift):
            drift[i].severity = item_info.get("severity")
            drift[i].rationale = item_info.get("rationale")

    ra = RiskAssessment(
        overall_score=float(parsed.get("overall_score", 0.0)),
        summary=parsed.get("summary", ""),
        items=drift,
    )
    return {"risk_assessment": ra, "drift": drift}
```

### 5.4 MitigationAgent

```python
# src/oscal_dtl/agents/mitigation.py
from __future__ import annotations

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import OPENAI_MODEL
from ..models import RiskAssessment, MitigationPlan

_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a security engineer. Given a risk assessment and drift items, "
            "propose concrete mitigation steps grouped by component. "
            "Be practical and concise."
        ),
        (
            "human",
            "Risk assessment:\n{risk_json}\n\n"
            "Return JSON with 'narrative' (text) and 'by_component' "
            "(mapping component -> list of actions)."
        ),
    ]
)

def mitigation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    ra: RiskAssessment = state.get("risk_assessment")
    if ra is None:
        return {}

    import json
    payload = {
        "overall_score": ra.overall_score,
        "summary": ra.summary,
        "items": [
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
        ],
    }

    msg = _PROMPT.format(risk_json=payload)
    resp = _llm.invoke(msg.to_messages())

    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {"narrative": resp.content, "by_component": {}}

    mp = MitigationPlan(
        narrative=parsed.get("narrative", ""),
        by_component=parsed.get("by_component", {}),
    )
    return {"mitigation_plan": mp}
```

### 5.5 DocumentorAgent

Creates “fake but OSCAL-shaped” updates: an assessment-result and POA&M fragment.

```python
# src/oscal_dtl/agents/documentor.py
from __future__ import annotations

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from ..config import OPENAI_MODEL
from ..models import RiskAssessment, MitigationPlan, DocumentationUpdate

_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an OSCAL expert. Given drifts, risk assessment, and mitigation plan, "
            "produce OSCAL-like JSON fragments for 'assessment-results' and 'plan-of-action-and-milestones' "
            "models. Use realistic but minimal structure (ids, description, status)."
        ),
        (
            "human",
            "Risk assessment:\n{risk_json}\n\n"
            "Mitigation plan:\n{mitigation_json}\n\n"
            "Return JSON with 'assessment_fragment' and 'poam_fragment'."
        ),
    ]
)

def documentor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    ra: RiskAssessment = state.get("risk_assessment")
    mp: MitigationPlan = state.get("mitigation_plan")
    if ra is None or mp is None:
        return {}

    import json
    risk_payload = {
        "overall_score": ra.overall_score,
        "summary": ra.summary,
        "items": [
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
        ],
    }

    mitigation_payload = {
        "narrative": mp.narrative,
        "by_component": mp.by_component,
    }

    msg = _PROMPT.format(
        risk_json=risk_payload,
        mitigation_json=mitigation_payload,
    )
    resp = _llm.invoke(msg.to_messages())

    try:
        parsed = json.loads(resp.content)
    except Exception:
        parsed = {
            "assessment_fragment": {"raw_text": resp.content},
            "poam_fragment": {"raw_text": resp.content},
        }

    du = DocumentationUpdate(
        assessment_fragment=parsed.get("assessment_fragment", {}),
        poam_fragment=parsed.get("poam_fragment", {}),
    )
    return {"documentation_update": du}
```

### 5.6 `cli.py` – run a “cycle” and print results

```python
# src/oscal_dtl/cli.py
from __future__ import annotations

from .graph import build_graph

def main():
    app = build_graph()

    # Empty initial state; graph will populate it
    result = app.invoke({})

    print("=== Drift detected ===")
    for d in result.get("drift", []):
        print(
            f"- [{d.severity or 'n/a'}] {d.component}.{d.attribute}: "
            f"expected={d.expected} observed={d.observed} controls={d.control_ids}"
        )

    ra = result.get("risk_assessment")
    if ra:
        print("\n=== Risk Assessment ===")
        print(f"Score: {ra.overall_score}")
        print(f"Summary: {ra.summary}")

    mp = result.get("mitigation_plan")
    if mp:
        print("\n=== Mitigation Plan ===")
        print(mp.narrative)
        for comp, actions in mp.by_component.items():
            print(f"  {comp}:")
            for a in actions:
                print(f"    - {a}")

    du = result.get("documentation_update")
    if du:
        print("\n=== OSCAL Assessment Fragment (demo) ===")
        print(du.assessment_fragment)
        print("\n=== OSCAL POA&M Fragment (demo) ===")
        print(du.poam_fragment)

if __name__ == "__main__":
    main()
```

Run:

```bash
export OPENAI_API_KEY=...
python -m oscal_dtl.cli
```

You now have a **full digital twin cycle**:

* detect drift
* assess risk
* propose mitigations
* generate OSCAL-style documentation updates

---

## 6. Minimal README you can paste

````markdown
# oscal-digital-twin-lab

A tiny playground for **OSCAL-powered digital twins** with **LangGraph agents**.

Inspired by NIST's CSWP 53 draft ("Charting the Course for NIST OSCAL") and its vision of
OSCAL-backed digital twins and agentic AI for continuous assurance, this repo simulates a
mini environment:

- An OSCAL SSP = the **intended** system state (the twin's “DNA”).
- A simple YAML **live-config** = the **actual** system state.
- A set of agents (LangGraph) that:
  - detect **drift** between the SSP and live config,
  - assess **risk**,
  - suggest **mitigation** actions, and
  - generate OSCAL-like **assessment / POA&M** fragments.

## Stack

- OSCAL examples from [`usnistgov/oscal-content`](https://github.com/usnistgov/oscal-content)
- [LangGraph](https://github.com/langchain-ai/langgraph) for agent orchestration
- [LangChain](https://github.com/langchain-ai/langchain) for LLM plumbing

## Quickstart

```bash
git clone https://github.com/<you>/oscal-digital-twin-lab.git
cd oscal-digital-twin-lab

# OSCAL content
git submodule add https://github.com/usnistgov/oscal-content.git data/oscal-content

pip install -U langgraph langchain langchain-community langchain-openai pydantic pyyaml
export OPENAI_API_KEY=...

python -m oscal_dtl.cli
````

You should see:

* drift between SSP expectations and live config,
* a computed risk score + summary,
* a proposed mitigation plan,
* and sample OSCAL-like JSON fragments that could be fed into real GRC tooling.

## Roadmap

* Map more complex attributes from real OSCAL SSP examples.
* Add a "scenario runner" to test *what-if* config changes.
* Add a small web UI to visualize drift over time.
* Integrate with `oscal-agent-lab` for shared catalogs / RAG.

```

---

If you want, next step we can:

- design a **scenario runner** (e.g., `python -m oscal_dtl.run_scenario mfa_off.yaml`), or  
- make a small **Streamlit UI** to toggle configs and watch drift/update in real time.
::contentReference[oaicite:6]{index=6}
```

[1]: https://github.com/usnistgov/oscal-content?utm_source=chatgpt.com "NIST SP 800-53 content and other OSCAL content examples"
[2]: https://csrc.nist.gov/pubs/cswp/53/charting-the-course-for-nist-oscal/ipd?utm_source=chatgpt.com "CSWP 53, Charting the Course for NIST OSCAL | CSRC"
[3]: https://docs.langchain.com/oss/python/langgraph/overview?utm_source=chatgpt.com "LangGraph overview - Docs by LangChain"
