from __future__ import annotations

from pydantic import BaseModel


class DashboardOverview(BaseModel):
    totals: dict[str, int]
    datasets_by_status: dict[str, int]
    events_by_verdict: dict[str, int]
    incidents_by_severity: dict[str, int]
    incidents_by_status: dict[str, int]
    top_attack_types: dict[str, int]
    risk: dict[str, float]
