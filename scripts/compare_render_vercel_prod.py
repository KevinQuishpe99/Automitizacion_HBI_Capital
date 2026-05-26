"""
Comparación en producción: Render vs Vercel (mismas rutas que EndpointViejosRender).

Uso:
  python scripts/compare_render_vercel_prod.py
  python scripts/compare_render_vercel_prod.py --poll-seconds 90
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

RENDER_BASE = "https://api-render-conware-powerautomate.onrender.com"
VERCEL_BASE = "https://automitizacion-hbi-capital.vercel.app"

DRY_RUN_BODY = json.dumps(
    {
        "report_date_iso": "2026-04-23",
        "merge_manifest_path": None,
        "historical_file_path": None,
    }
).encode("utf-8")


def http_json(
    method: str,
    url: str,
    body: bytes | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any] | list[Any] | str | None]:
    headers = {"User-Agent": "hbi-prod-compare/1.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except Exception as exc:
        return 0, str(exc)

    if not raw.strip():
        return code, None
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError:
        return code, raw[:500]


def poll_job(
    base: str,
    job_id: str,
    *,
    max_wait: float,
    interval: float = 5.0,
) -> dict[str, Any]:
    url = f"{base}/graph/sharepoint/payment-validation/jobs/{job_id}"
    deadline = time.time() + max_wait
    last: dict[str, Any] = {}
    while time.time() < deadline:
        code, data = http_json("GET", url, timeout=30.0)
        if code != 200 or not isinstance(data, dict):
            last = {"http": code, "raw": data}
            time.sleep(interval)
            continue
        last = data
        status = str(data.get("status") or "")
        if status in ("completed", "failed", "expired"):
            return last
        time.sleep(interval)
    last["_poll_timeout"] = True
    return last


def compare_queue_shape(render_data: Any, vercel_data: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(render_data, dict) or not isinstance(vercel_data, dict):
        return ["queue response no es objeto JSON en uno de los dos"]
    for key in ("job_id", "status"):
        if key not in vercel_data:
            issues.append(f"Vercel falta campo queue: {key}")
        if key not in render_data:
            issues.append(f"Render falta campo queue: {key}")
    if render_data.get("status") != vercel_data.get("status"):
        issues.append(
            f"status queue distinto: render={render_data.get('status')} "
            f"vercel={vercel_data.get('status')}"
        )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll-seconds", type=float, default=120.0)
    parser.add_argument(
        "--release-locks",
        action="store_true",
        help="Libera locks generate/finalize en Vercel antes de probar",
    )
    args = parser.parse_args()

    if args.release_locks:
        code, data = http_json(
            "POST",
            f"{VERCEL_BASE}/diagnostics/payment-validation/locks/release",
            timeout=20.0,
        )
        print(f"[locks] release http={code} {data}")

    results: list[dict[str, Any]] = []

    def record(name: str, **kwargs: Any) -> None:
        row = {"test": name, **kwargs}
        results.append(row)
        ok = row.get("ok", False)
        mark = "OK" if ok else "FAIL"
        print(f"[{mark}] {name}")
        if row.get("detail"):
            print(f"       {row['detail']}")

    # 1) Health
    for label, base in (("render", RENDER_BASE), ("vercel", VERCEL_BASE)):
        code, data = http_json("GET", f"{base}/health", timeout=20.0)
        record(
            f"health_{label}",
            ok=code == 200 and isinstance(data, dict) and data.get("status") == "ok",
            http=code,
            detail=data,
        )

    # 2) Runtime config (Vercel)
    code, data = http_json("GET", f"{VERCEL_BASE}/diagnostics/runtime-config-safe", timeout=20.0)
    record(
        "vercel_runtime_config",
        ok=code == 200
        and isinstance(data, dict)
        and data.get("has_blob_token") is True
        and data.get("store_class") == "VercelBlobJobStore",
        http=code,
        detail=data,
    )

    # 3) Workflow ping (Vercel)
    code, q = http_json("POST", f"{VERCEL_BASE}/diagnostics/workflow-ping/queue", timeout=30.0)
    ping_ok = (
        code == 202
        and isinstance(q, dict)
        and q.get("status") == "queued"
        and bool(q.get("job_id"))
    )
    ping_final: dict[str, Any] = {}
    if ping_ok:
        ping_final = poll_job(
            VERCEL_BASE,
            str(q["job_id"]),
            max_wait=min(args.poll_seconds, 45.0),
        )
        ping_ok = str(ping_final.get("status")) == "completed"
    record(
        "vercel_workflow_ping",
        ok=ping_ok,
        http=code,
        detail={"queued": q, "final": ping_final},
    )

    # 4) Dry-run queue shape
    r_code, r_q = http_json(
        "POST",
        f"{RENDER_BASE}/graph/sharepoint/payment-validation/amortization/dry-run/queue",
        body=DRY_RUN_BODY,
        timeout=30.0,
    )
    v_code, v_q = http_json(
        "POST",
        f"{VERCEL_BASE}/graph/sharepoint/payment-validation/amortization/dry-run/queue",
        body=DRY_RUN_BODY,
        timeout=30.0,
    )
    shape_issues = compare_queue_shape(r_q, v_q)
    record(
        "dry_run_queue_shape",
        ok=r_code in (200, 202) and v_code in (200, 202) and not shape_issues,
        detail={
            "render_http": r_code,
            "vercel_http": v_code,
            "issues": shape_issues,
            "render": r_q,
            "vercel": v_q,
        },
    )

    # 5) Dry-run ejecución (poll)
    dry_ok = False
    dry_detail: dict[str, Any] = {}
    if isinstance(r_q, dict) and r_q.get("job_id") and isinstance(v_q, dict) and v_q.get("job_id"):
        r_final = poll_job(RENDER_BASE, str(r_q["job_id"]), max_wait=args.poll_seconds)
        v_final = poll_job(VERCEL_BASE, str(v_q["job_id"]), max_wait=args.poll_seconds)
        r_st = str(r_final.get("status"))
        v_st = str(v_final.get("status"))
        dry_ok = r_st == v_st and r_st in ("completed", "failed")
        if r_st != v_st:
            dry_detail["status_mismatch"] = {"render": r_st, "vercel": v_st}
        dry_detail["render"] = {
            "status": r_st,
            "error_type": (r_final.get("error") or {}).get("type")
            if isinstance(r_final.get("error"), dict)
            else None,
        }
        dry_detail["vercel"] = {
            "status": v_st,
            "error_type": (v_final.get("error") or {}).get("type")
            if isinstance(v_final.get("error"), dict)
            else None,
        }
        if r_st == "failed" and v_st == "failed":
            dry_detail["note"] = "ambos failed (comparar error_code manualmente)"
            dry_ok = True
    record("dry_run_execution", ok=dry_ok, detail=dry_detail)

    # 6) Setup merge-control (síncrono)
    for label, base in (("render", RENDER_BASE), ("vercel", VERCEL_BASE)):
        code, data = http_json(
            "POST",
            f"{base}/graph/sharepoint/payment-validation/setup/merge-control-workbook",
            timeout=120.0,
        )
        record(
            f"setup_merge_control_{label}",
            ok=code in (200, 201),
            http=code,
            detail=data if isinstance(data, dict) else str(data)[:200],
        )

    # Resumen
    failed = [r["test"] for r in results if not r.get("ok")]
    print("\n=== RESUMEN ===")
    print(f"Total: {len(results)}, OK: {len(results) - len(failed)}, FAIL: {len(failed)}")
    if failed:
        print("Fallidos:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
