"""Obtiene error de un job en producción Vercel."""
import json
import sys
import time
import urllib.request

BASE = "https://automitizacion-hbi-capital.vercel.app"


def post_queue(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def get_job(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode())


def wait_job(path: str, max_sec: int = 300) -> dict:
    deadline = time.time() + max_sec
    while time.time() < deadline:
        j = get_job(path)
        if j.get("status") in ("completed", "failed"):
            return j
        time.sleep(8)
    return get_job(path)


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "generate"
    if kind == "generate":
        q = post_queue("/graph/sharepoint/payment-validation/generate/queue")
        path = f"/graph/sharepoint/payment-validation/jobs/{q['job_id']}"
    elif kind == "notify":
        q = post_queue(
            "/graph/sharepoint/notify-validar-extractos-email",
            {
                "historical_file_path": (
                    "INFORMACION CREDITOS-CLIENTES/02 COMWARE - VALIDACION PAGOS/"
                    "02 HISTORICO/cartera_validada_2026-05-22.xlsx"
                )
            },
        )
        path = f"/graph/sharepoint/notify-validar-extractos-email/jobs/{q['job_id']}"
    else:
        raise SystemExit("usage: generate|notify")
    print("queued", q)
    j = wait_job(path)
    print(json.dumps(j, indent=2, ensure_ascii=False)[:4000])
