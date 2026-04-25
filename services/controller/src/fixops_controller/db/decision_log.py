from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fixops_controller.db.models import DecisionLogEntry


async def append_decision(
    session: AsyncSession,
    investigation_id: str,
    step: str,
    payload: dict[str, Any],
) -> None:
    row = DecisionLogEntry(investigation_id=investigation_id, step=step, payload=payload)
    session.add(row)
    await session.commit()
