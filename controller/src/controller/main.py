from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from fixops_contract.models import AlertPayload

from controller.config import ControllerSettings
from controller.orchestrator import run_investigation
from controller.render import print_report
from controller.worker_client import WorkerK8sNotConfigured, WorkerK8sTransportError

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def investigate(
    alert_file: Path,
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit full InvestigationReport as JSON (for automation). Default: formatted summary.",
    ),
) -> None:
    """Load a normalized alert JSON and run the investigation pipeline."""
    alert = AlertPayload.model_validate_json(alert_file.read_text(encoding="utf-8"))
    ctrl = ControllerSettings()
    try:
        report = run_investigation(settings=ctrl, alert=alert)
    except WorkerK8sNotConfigured as e:
        console.print(f"[bold red]K8s worker not configured.[/bold red]\n{e}")
        raise typer.Exit(code=1) from e
    except WorkerK8sTransportError as e:
        console.print(f"[bold red]K8s worker not available.[/bold red]\n{e}")
        raise typer.Exit(code=1) from e
    print_report(console, report, as_json=json_out)
    console.print(f"[dim]Logged to {ctrl.decision_log_path}[/dim]")


@app.command("print-alert-schema")
def print_alert_schema() -> None:
    """Dump AlertPayload JSON schema for integrations."""
    console.print(json.dumps(AlertPayload.model_json_schema(), indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
