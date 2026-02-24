from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from oscal_dtl import cli


class FakeApp:
    def invoke(self, _state):
        drift_item = SimpleNamespace(
            component="web-app",
            attribute="mfa_enabled",
            expected=True,
            observed=False,
            control_ids=["IA-2"],
            severity="high",
            rationale="MFA disabled",
        )
        return {
            "drift": [drift_item],
            "risk_assessment": None,
            "mitigation_plan": None,
            "documentation_update": None,
        }


def test_help_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["oscal-dtl", "--help"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0


def test_json_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["oscal-dtl", "--json", "--skip-validation"])
    monkeypatch.setattr(cli, "build_graph", lambda: FakeApp())

    rc = cli.main()

    assert rc == 0
    out = capsys.readouterr().out
    json_start = out.index("{")
    payload = json.loads(out[json_start:])
    assert payload["drift"][0]["component"] == "web-app"


def test_validation_error_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["oscal-dtl"])
    monkeypatch.setattr(cli, "validate_config", lambda: ["OPENAI_API_KEY missing"])

    rc = cli.main()

    assert rc == 1
    err = capsys.readouterr().err
    assert "Configuration errors:" in err
