"""Smoke checks en build Vercel: dependencias y compat Workflows SDK."""

from __future__ import annotations

import sys


def main() -> int:
    import fastapi

    print(f"fastapi ok ({fastapi.__version__})")

    from app.workflows.vercel_sdk_compat import (
        apply_vercel_workflow_event_result_compat,
        vercel_package_version,
    )

    vercel_ver = vercel_package_version()
    print(f"vercel ok ({vercel_ver})")

    apply_vercel_workflow_event_result_compat()
    from vercel._internal.workflow import world as w

    parsed = w.EventResult.model_validate({"cursor": "eid:test", "hasMore": False})
    print(f"EventResult compat ok (has_more={parsed.has_more})")

    from index import app

    print(f"index import ok ({type(app).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
