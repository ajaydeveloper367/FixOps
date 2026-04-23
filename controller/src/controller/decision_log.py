from __future__ import annotations

import json
from pathlib import Path

from fixops_contract.models import InvestigationReport


def append_report(path: Path, report: InvestigationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(report.model_dump_json() + "\n")


def load_tail(path: Path, *, max_lines: int = 5) -> list[InvestigationReport]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-max_lines:]
    return [InvestigationReport.model_validate_json(line) for line in lines if line.strip()]
