"""Ejecución inline de amortization dry-run (fallback API cuando el worker no corre)."""

from __future__ import annotations

from typing import Any

from app.adapters.primary.http.deps import get_graph_client, init_graph_client
from app.adapters.secondary.ms_graph_client import MsGraphClient
from app.application.jobs.amortization_dry_run_job import execute_amortization_dry_run_job


async def execute_amortization_dry_run_job_with_graph(
    job_id: str,
    *,
    report_date_iso: str | None,
    merge_manifest_path: str | None,
    historical_file_path: str | None,
) -> None:
    """Misma inicialización Graph que el step durable del workflow."""
    init_graph_client(MsGraphClient())
    graph: Any = get_graph_client()
    await execute_amortization_dry_run_job(
        job_id,
        graph,
        report_date_iso=report_date_iso,
        merge_manifest_path=merge_manifest_path,
        historical_file_path=historical_file_path,
    )
