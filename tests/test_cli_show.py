"""``fixops-show`` Rich renderer (stdin / file)."""

from __future__ import annotations

import json
from io import StringIO

import pytest

pytest.importorskip("rich")

from fixops_controller.cli.show import render_investigation_envelope


def test_render_investigation_envelope_contains_sections() -> None:
    from rich.console import Console

    buf = StringIO()
    console = Console(file=buf, width=100, force_terminal=False, color_system=None)
    envelope = {
        "status": "awaiting_approval",
        "thread_id": "t-demo",
        "interrupts": [
            {
                "value": {
                    "rca_summary": "Something is wrong.",
                    "confidence_band": "medium",
                },
            }
        ],
        "state": {
            "investigation_id": "inv-1",
            "confidence_band": "medium",
            "normalized": {
                "raw": {
                    "alertname": "TargetDown",
                    "namespace": "monitoring",
                    "pod": "pod-abc",
                },
            },
            "route": {"worker_id": "worker-obs", "worker_base_url": "http://127.0.0.1:8081"},
            "merged": {
                "checked": ["prometheus instant query: up{}"],
                "findings": ["Found 9 series"],
                "ruled_out": ["No series for default"],
                "confidence": 0.82,
            },
            "rca": {
                "summary": "RCA one-liner.",
                "root_cause_hypothesis": "Maybe labels.",
                "recommended_next_steps": ["Step A", "Step B"],
            },
            "errors": [],
        },
    }
    render_investigation_envelope(envelope, console=console)
    out = buf.getvalue()
    assert "t-demo" in out
    assert "awaiting_approval" in out or "awaiting" in out.lower()
    assert "TargetDown" in out
    assert "monitoring" in out
    assert "What was checked" in out
    assert "Evidence" in out
    assert "Conclusion" in out
    assert "Action items" in out
    assert "Step A" in out


def test_main_reads_json_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fixops_controller.cli import show as show_mod

    p = tmp_path / "out.json"
    p.write_text(json.dumps({"status": "completed", "thread_id": "x", "state": {}}), encoding="utf-8")
    monkeypatch.setattr("sys.stdout", StringIO())
    show_mod.main(["--no-color", str(p)])
    # no crash
