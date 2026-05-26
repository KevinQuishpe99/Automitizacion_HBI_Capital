"""Compara notify Render vs Vercel en producción."""
import json
import time
import urllib.request

RENDER = "https://api-render-conware-powerautomate.onrender.com"
VERCEL = "https://automitizacion-hbi-capital.vercel.app"
BODY = {
    "historical_file_path": (
        "INFORMACION CREDITOS-CLIENTES/02 COMWARE - VALIDACION PAGOS/"
        "02 HISTORICO/cartera_validada_2026-05-22.xlsx"
    )
}


def post(base: str) -> dict:
    data = json.dumps(BODY).encode()
    req = urllib.request.Request(
        f"{base}/graph/sharepoint/notify-validar-extractos-email",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def get_job(base: str, job_id: str) -> dict:
    with urllib.request.urlopen(
        f"{base}/graph/sharepoint/notify-validar-extractos-email/jobs/{job_id}",
        timeout=30,
    ) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    for label, base in (("render", RENDER), ("vercel", VERCEL)):
        q = post(base)
        jid = q["job_id"]
        print(f"{label} queued {jid}")
        for _ in range(25):
            j = get_job(base, jid)
            st = j.get("status")
            if st in ("completed", "failed"):
                err = j.get("error") or {}
                print(
                    label,
                    st,
                    err.get("error_code") or err.get("type"),
                    (err.get("message") or "")[:200],
                )
                break
            time.sleep(10)


if __name__ == "__main__":
    main()
