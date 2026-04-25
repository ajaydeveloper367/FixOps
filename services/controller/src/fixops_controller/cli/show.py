"""Pretty-print investigation JSON from ``curl`` / file (Rich terminal UI — optional ``[terminal]`` extra)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _require_rich():
    try:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
    except ImportError as e:  # pragma: no cover - exercised when rich missing
        sys.stderr.write(
            "Rich is required for fixops-show. Install:\n"
            "  uv sync --group dev\n"
            "or:  uv pip install 'fixops-controller[terminal]'\n"
        )
        raise SystemExit(1) from e
    return Console, Panel, Table, Text, box


def _rich_widgets():
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    return Panel, Table, Text, box


def _as_text(v: Any, max_len: int = 1200) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        s = v.strip()
    elif isinstance(v, (dict, list)):
        s = json.dumps(v, indent=2, default=str)
    else:
        s = str(v).strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def render_investigation_envelope(envelope: dict[str, Any], *, console: Any) -> None:
    """Render controller ``/run`` / ``/resume`` JSON envelope with Rich panels."""
    Panel, Table, Text, box = _rich_widgets()

    state = envelope.get("state") or {}
    normalized = state.get("normalized") or {}
    raw = normalized.get("raw") if isinstance(normalized.get("raw"), dict) else {}
    route = state.get("route") or {}
    merged = state.get("merged") or {}
    rca = state.get("rca") or {}

    status = _as_text(envelope.get("status"), 80) or "unknown"
    thread_id = _as_text(envelope.get("thread_id"), 200) or "—"
    inv = _as_text(state.get("investigation_id"), 80)
    band = _as_text(state.get("confidence_band"), 40)
    conf = merged.get("confidence")
    try:
        conf_s = f"{float(conf):.2f}" if conf is not None else "—"
    except (TypeError, ValueError):
        conf_s = "—"

    # --- Header ---
    hdr = Text()
    hdr.append("Thread ", style="dim")
    hdr.append(thread_id, style="bold cyan")
    hdr.append("  ·  ", style="dim")
    hdr.append("Status ", style="dim")
    hdr.append(status, style="bold yellow")
    if inv:
        hdr.append("\n", style="dim")
        hdr.append("Investigation ", style="dim")
        hdr.append(inv, style="bold white")
    console.print(Panel(hdr, title="[bold]FixOps investigation[/]", border_style="blue", box=box.ROUNDED))
    console.print()

    # --- Alert ---
    title = _as_text(raw.get("alertname") or raw.get("alert_class"), 120) or "Operational alert"
    alert_lines = Text()
    alert_lines.append(title + "\n", style="bold white")
    ns = _as_text(raw.get("namespace"), 80)
    pod = _as_text(raw.get("pod"), 160)
    if ns:
        alert_lines.append("Namespace: ", style="dim")
        alert_lines.append(ns + "\n", style="white")
    if pod:
        alert_lines.append("Pod: ", style="dim")
        alert_lines.append(pod + "\n", style="white")
    wk = _as_text(route.get("worker_id"), 80)
    if wk:
        alert_lines.append("\nWorker: ", style="dim")
        alert_lines.append(wk, style="cyan")
        alert_lines.append("  ·  ", style="dim")
        alert_lines.append("Band ", style="dim")
        alert_lines.append(band or "—", style="magenta")
        alert_lines.append("  ·  merged ", style="dim")
        alert_lines.append(conf_s, style="green")

    intr = envelope.get("interrupts") or []
    if intr:
        v0 = (intr[0] or {}).get("value") or {}
        summ = _as_text(v0.get("rca_summary"), 800)
        if summ:
            alert_lines.append("\n\n", style="dim")
            alert_lines.append(summ, style="italic")

    console.print(Panel(alert_lines, title="[bold]Alert[/]", border_style="cyan", box=box.ROUNDED))
    console.print()

    # --- What was checked ---
    checked = merged.get("checked")
    if isinstance(checked, list) and checked:
        t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        t.add_column("", style="dim", width=3)
        t.add_column("", style="white")
        for i, line in enumerate(checked[:30], start=1):
            t.add_row(f"{i}.", _as_text(line, 500))
        console.print(Panel(t, title="[bold]What was checked[/]", border_style="white", box=box.ROUNDED))
        console.print()

    # --- Evidence ---
    findings = merged.get("findings") if isinstance(merged.get("findings"), list) else []
    ruled = merged.get("ruled_out") if isinstance(merged.get("ruled_out"), list) else []
    if findings or ruled:
        ev = Text()
        if findings:
            ev.append("Findings\n", style="bold")
            for f in findings[:12]:
                ev.append("  • ", style="dim")
                ev.append(_as_text(f, 500) + "\n", style="white")
            ev.append("\n", style="dim")
        if ruled:
            ev.append("Ruled out / no match\n", style="bold")
            for r in ruled[:10]:
                ev.append("  • ", style="dim")
                ev.append(_as_text(r, 500) + "\n", style="yellow")
        console.print(Panel(ev, title="[bold]Evidence[/]", border_style="white", box=box.ROUNDED))
        console.print()

    # --- Conclusion ---
    summ = _as_text(rca.get("summary"), 2000)
    hyp = _as_text(rca.get("root_cause_hypothesis"), 2000)
    if summ or hyp:
        concl = Text()
        concl.append(
            "Summaries come from the worker AD-006 contract (compact checks), not full raw log dumps.\n\n",
            style="dim italic",
        )
        if summ:
            concl.append(summ + "\n\n", style="white")
        if hyp:
            concl.append("Hypothesis: ", style="bold")
            concl.append(hyp, style="italic")
        console.print(Panel(concl, title="[bold]Conclusion[/]", border_style="magenta", box=box.ROUNDED))
        console.print()

    # --- Action items ---
    steps = rca.get("recommended_next_steps")
    if isinstance(steps, list) and steps:
        at = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        at.add_column("", style="bold green", width=3)
        at.add_column("", style="white")
        for i, s in enumerate(steps[:15], start=1):
            at.add_row(f"{i}.", _as_text(s, 600))
        console.print(Panel(at, title="[bold]Action items[/]", border_style="green", box=box.ROUNDED))
        console.print()

    errs = state.get("errors") or []
    if isinstance(errs, list) and errs:
        et = Text()
        for e in errs[:10]:
            et.append(f"• {_as_text(e, 500)}\n", style="red")
        console.print(Panel(et, title="[bold]Errors[/]", border_style="red", box=box.ROUNDED))
        console.print()

    if envelope.get("planning"):
        pm = _as_text((envelope.get("planning") or {}).get("planner_mode"), 20)
        if pm:
            console.print(f"[dim]Planner mode: {pm}[/dim]")


def _load_json(args: argparse.Namespace) -> dict[str, Any]:
    raw: str
    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        sys.stderr.write(
            "Usage:\n"
            "  curl -sS ... | fixops-show\n"
            "  fixops-show path/to/response.json\n"
        )
        raise SystemExit(2)
    data = json.loads(raw)
    if not isinstance(data, dict):
        sys.stderr.write("Top-level JSON must be an object.\n")
        raise SystemExit(2)
    return data


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Pretty-print FixOps investigation JSON (Rich).")
    p.add_argument(
        "file",
        nargs="?",
        help="Path to JSON file (otherwise read stdin)",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors",
    )
    args = p.parse_args(argv)

    Console, *_ = _require_rich()
    import os

    if args.no_color:
        os.environ["NO_COLOR"] = "1"

    console = Console(soft_wrap=True)
    envelope = _load_json(args)
    render_investigation_envelope(envelope, console=console)


if __name__ == "__main__":
    main()
