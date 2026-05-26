# Smoke test — Vercel Workflow (HBI Capital)

Validación post-migración de endpoints pesados. Sustituye `BASE_URL` por tu despliegue Vercel (o `http://127.0.0.1:8000` en local).

## Variables requeridas en Vercel

Ver [`.env.vercel.example`](../.env.vercel.example):

- `JOB_STORE_BACKEND=vercel_blob`
- `JOB_RUNNER_BACKEND=vercel_workflow`
- `VERCEL_WORKFLOWS_ENABLED=true`
- `BLOB_READ_WRITE_TOKEN`, `BLOB_STORE_ID`
- Todos los `WORKFLOW_*_NAME` (defaults en `job_runner_settings.py`)
- `VERCEL_WORKFLOW_API_FALLBACK=true` (recomendado)
- Variables `GRAPH_*` (mismas que Render)

## Pre-check (sin Graph)

```bash
export BASE_URL=https://tu-app.vercel.app

curl -sS "$BASE_URL/health" | jq .
curl -sS "$BASE_URL/diagnostics/runtime-config-safe" | jq .
curl -sS "$BASE_URL/diagnostics/graph-env-present" | jq .
```

Esperado: `job_runner_backend` = `vercel_workflow`, `job_store_backend` = `vercel_blob`.

## Ping de workflow (recomendado primero)

```bash
JOB=$(curl -sS -X POST "$BASE_URL/diagnostics/workflow-ping/queue" | jq -r .job_id)
echo "job_id=$JOB"
sleep 15
curl -sS "$BASE_URL/diagnostics/workflow-ping/jobs/$JOB" | jq .
curl -sS "$BASE_URL/diagnostics/workflow-ping/jobs/$JOB/markers" | jq .
```

Esperado: `status` pasa de `queued` → `running` → `completed`.

---

## Endpoints migrados — encolar (202 + job_id + status queued)

### 1. Validate payment report (queue)

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/validate-payment-report/queue" | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/validate-payment-report/jobs/$JOB" | jq .
```

### 2. Payment validation — generate

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/payment-validation/generate/queue" \
  -H "Content-Type: application/json" -d '{}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/payment-validation/jobs/$JOB" | jq .
```

### 3. Payment validation — finalize

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/payment-validation/finalize/queue" \
  -H "Content-Type: application/json" -d '{"validation_file_path":"revision/ejemplo.xlsx"}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/payment-validation/jobs/$JOB" | jq .
```

### 4. Notify validar extractos

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/notify-validar-extractos-email" \
  -H "Content-Type: application/json" \
  -d '{"historical_file_path":"ruta/al/historico.xlsx"}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/notify-validar-extractos-email/jobs/$JOB" | jq .
```

### 5. Merge composite validado PDFs

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/merge-composite-validado-pdfs" \
  -H "Content-Type: application/json" -d '{"force_rebuild":false}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/merge-composite-validado-pdfs/jobs/$JOB" | jq .
```

### 6. Ensure asientos contables

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/ensure-asientos-contables-folders" | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/ensure-asientos-contables-folders/jobs/$JOB" | jq .
```

### 7. Amortization dry-run

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/payment-validation/amortization/dry-run/queue" \
  -H "Content-Type: application/json" \
  -d '{"report_date_iso":"2026-05-15"}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/payment-validation/jobs/$JOB" | jq .
```

### 8. Amortization apply

```bash
JOB=$(curl -sS -X POST "$BASE_URL/graph/sharepoint/payment-validation/amortization/apply/queue" \
  -H "Content-Type: application/json" \
  -d '{"report_date_iso":"2026-05-15"}' | jq -r .job_id)
curl -sS "$BASE_URL/graph/sharepoint/payment-validation/jobs/$JOB" | jq .
```

---

## Script automatizado

```bash
bash scripts/smoke_test_vercel.sh https://tu-app.vercel.app
```

En Windows (Git Bash o WSL):

```bash
export BASE_URL=https://tu-app.vercel.app
bash scripts/smoke_test_vercel.sh
```

## Local con BackgroundTasks (Render-like)

```bash
export JOB_RUNNER_BACKEND=background
export JOB_STORE_BACKEND=memory
export VERCEL_WORKFLOWS_ENABLED=false
uvicorn app.main:app --reload
bash scripts/smoke_test_vercel.sh http://127.0.0.1:8000
```

## Qué NO probar como workflow

- `POST /graph/sharepoint/validate-payment-report` (síncrono legacy)
- `POST /parse-excel` con `excel_base64` en body
- `PUT .../item-content` con `content_base64`

Esos endpoints no pasan por `get_job_runner()`.
