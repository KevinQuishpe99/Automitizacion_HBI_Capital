"""Compat SDK Vercel Workflows: EventResult cursor/hasMore y versión del paquete."""

from __future__ import annotations

import pydantic
import pytest

from app.workflows.vercel_sdk_compat import (
    apply_vercel_workflow_event_result_compat,
    vercel_package_version,
)


def test_vercel_package_version_readable() -> None:
    ver = vercel_package_version()
    assert ver != "unknown"
    parts = ver.split(".")
    assert len(parts) >= 2
    assert int(parts[0]) >= 0


def test_event_result_accepts_cursor_and_has_more() -> None:
    apply_vercel_workflow_event_result_compat()
    from vercel._internal.workflow import world as w

    result = w.EventResult.model_validate(
        {
            "cursor": "eid:01TEST",
            "hasMore": False,
        }
    )
    assert result.cursor == "eid:01TEST"
    assert result.has_more is False


def test_event_result_compat_idempotent() -> None:
    apply_vercel_workflow_event_result_compat()
    from vercel._internal.workflow import world as w

    first = w.EventResult
    apply_vercel_workflow_event_result_compat()
    assert w.EventResult is first


def test_original_event_result_would_reject_cursor() -> None:
    """Documenta la causa: BaseModel del SDK usa extra=forbid sin campos de paginación."""
    from vercel._internal.workflow.world import BaseModel
    from pydantic import Field
    from typing import Any

    class StrictEventResult(BaseModel):
        event: Any | None = None
        cursor: str | None = None
        has_more: bool | None = Field(default=None, alias="hasMore")

    ok = StrictEventResult.model_validate({"cursor": "x", "hasMore": True})
    assert ok.cursor == "x"

    class StrictNoCursor(BaseModel):
        pass

    with pytest.raises(pydantic.ValidationError, match="extra_forbidden"):
        StrictNoCursor.model_validate({"cursor": "x", "hasMore": True})
