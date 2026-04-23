"""Human-friendly CLI rendering (machine output stays JSON)."""

from __future__ import annotations

import json

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from fixops_contract.models import InvestigationReport


def print_report(console: Console, report: InvestigationReport, *, as_json: bool) -> None:
    if as_json:
        console.print(json.dumps(report.model_dump(), indent=2))
        return

    title = report.alert.title or "Investigation"
    sub = (report.alert.message or "").strip()
    if len(sub) > 280:
        sub = sub[:280] + "…"
    console.print(
        Panel(
            f"[bold]{title}[/bold]\n[dim]{sub}[/dim]\n\n"
            f"Worker: [cyan]{report.routed_worker}[/cyan]   "
            f"Confidence: [yellow]{report.worker.confidence:.2f}[/yellow]",
            title="Alert",
            border_style="blue",
        )
    )

    if report.conclusion:
        console.print(
            Panel(
                Markdown(report.conclusion),
                title="Conclusion",
                border_style="magenta",
            )
        )

    if report.root_cause_summary:
        console.print(
            Panel(
                report.root_cause_summary,
                title="Root cause (from cluster evidence)",
                border_style="red",
            )
        )

    if report.action_items:
        md = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(report.action_items))
        console.print(Panel(Markdown(md), title="Action items", border_style="green"))

    tbl = Table(title="What was checked", show_header=False, pad_edge=False)
    tbl.add_column("ref", style="dim")
    for c in report.worker.checked[:40]:
        tbl.add_row(c)
    if len(report.worker.checked) > 40:
        tbl.add_row(f"… ({len(report.worker.checked) - 40} more)")
    console.print(tbl)

    if report.summary_lines:
        console.print("[bold]Summary[/bold]")
        for line in report.summary_lines:
            console.print(f"  • {line}")

    console.print(
        "\n[dim]Full worker JSON: pass --json  |  Decision log appended for automation.[/dim]"
    )
