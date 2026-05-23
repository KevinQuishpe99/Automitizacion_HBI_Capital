# Design: Migración backend FastAPI Render → Vercel Pro (100% Vercel)

## Technical Approach

Migrar el backend sin cambiar rutas públicas ni lógica de negocio: FastAPI sigue siendo la API HTTP; los procesos largos pasan de `BackgroundTasks`/`asyncio.create_task` + RAM a **Vercel Workflows** (orquestación durable) con **Vercel Blob** como fuente de verdad del documento de job que consume Power Automate. No se usa Redis, Postgres ni workers externos.

## Architecture Decisions

| Decisión | Elección | Alternativas | Rationale |
|----------|--------|--------------|-----------|
| Estado de jobs | **Vercel Blob** (`jobs/{id}/meta.json`, `result` separado) | Workflow state only | PA hace polling HTTP; Blob es legible desde cualquier invocación GET |
| Procesos largos | **Vercel Workflows** (`@wf.workflow` + `@wf.step`) | Solo Queues | Workflows = pasos, reintentos, >800s total; Queues es primitivo bajo nivel |
| Capa Queue explícita | **No** (solo Workflows) | Queues + Workflow | SDK Queues documentado para Node; Python beta Workflows arranca runs desde API |
| Entrypoint | **`app/main.py`** (`app = create_app()`) | `api/index.py` | Ya existe; Vercel lo detecta |
| JobStore local | `MemoryJobStore` | — | Paridad dev/test sin Blob |
| Unificación jobs | Un `JobStore` + rutas GET existentes leen el mismo store | Dos dicts | Elimina `_validation_jobs` vs `JobManager` |

## Data Flow

```
Power Automate
    │ POST */queue  (202, <2s)
    ▼
FastAPI (Vercel Function, maxDuration bajo)
    ├─ JobStore.create_job → Blob jobs/{job_id}/meta.json  [status=queued]
    ├─ WorkflowClient.start(type, job_id, payload)
    └─ return { job_id, status: "queued" }

Power Automate
    │ GET /jobs/{job_id}  (poll)
    ▼
FastAPI GET handler
    ├─ JobStore.get_job(job_id)  ← Blob meta (+ result inline o result_ref)
    └─ enrich_job_for_http_response(job)  [sin cambios de contrato PA]

Vercel Workflow (async, durable)
    ├─ step: acquire_lock
    ├─ step: update_job(running)
    ├─ step(s): invoke existing use case  [generate|finalize|merge|...]
    ├─ step: persist_result (Blob si > umbral)
    ├─ step: complete_job | fail_job
    └─ step: release_lock
```

## JobStore Interface

```python
class JobStore(Protocol):
    async def create_job(self, job_id: str, record: dict) -> None: ...
    async def get_job(self, job_id: str) -> dict | None: ...
    async def update_job(self, job_id: str, updates: dict) -> None: ...
    async def complete_job(self, job_id: str, result: dict) -> None: ...
    async def fail_job(self, job_id: str, error: dict) -> None: ...
    async def append_event(self, job_id: str, event: dict) -> None: ...  # opcional
    async def acquire_lock(self, key: str, holder: str, ttl_seconds: int) -> bool: ...
    async def release_lock(self, key: str, holder: str) -> None: ...
```

**Implementaciones:** `MemoryJobStore` (Fase 2), `VercelBlobJobStore` (Fase 3).

**TTL:** `expires_at` en `meta.json`; GET devuelve job con `status=expired` si pasó TTL (30 días propuesto).

## Blob Layout

| Path | Contenido |
|------|-----------|
| `jobs/{job_id}/meta.json` | status, type, timestamps, request, workflow_run_id, locks, result_ref |
| `jobs/{job_id}/result.json` | resultado si ≤ ~2 MB serializado |
| `results/{job_id}/full.json` | resultado grande (merge, dry-run items) |
| `locks/{key}.json` | `{holder_job_id, acquired_at, expires_at}` |
| `jobs/{job_id}/events.ndjson` | opcional, auditoría |

**Umbral inline vs ref:** si `len(json) > 2_000_000` → `result_ref` + `result_summary` en meta (conteos, paths, status agregado).

## Workflows por proceso

| Proceso | Workflow | Pasos (resumen) | >800s |
|---------|----------|-----------------|-------|
| amortization_dry_run | `wf_amortization_dry_run` | lock? → running → `run_amortization_fill_dry_run` → persist → complete | Dividir por tabla si un step falla timeout |
| amortization_apply | `wf_amortization_apply` | lock tabla/manifest → preflight step → apply por tabla (1 step/tabla) → verify step → complete | Sí, N tablas = N steps |
| merge PDFs | `wf_merge_composite` | running → `merge_composite_validado_pdfs` → persist | Un step si <800s; si no, split por id_pago |
| notify | `wf_notify_extractos` | running → `send_validar_extractos_notification_email` | Un step |
| generate | `wf_generate` | acquire `generate_finalize` lock → running → generate (sub-steps: bank / customers / excel / upload) | Varios steps |
| finalize | `wf_finalize` | acquire lock → running → finalize (sub-steps: hist / audit / upload) | Varios steps |

Cada **step** llama código existente en `app/application/use_cases/` sin cambiar reglas financieras.

## Locks (reemplazo flags memoria)

| Lock key | Reemplaza | TTL |
|----------|-----------|-----|
| `payment-validation:generate_finalize` | `_generate_active`, `_finalize_active` | 900s |
| `amortization:table:{normalized_path}` | exclusión concurrente por tabla | 600s |
| `amortization:manifest:{date}` | opcional, apply mismo día | 600s |

`acquire_lock` falla → job `failed` con código `LOCK_NOT_ACQUIRED` y HTTP 409 en POST si aplica.

## FastAPI en Vercel

**`vercel.json` (borrador):**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "app/main.py": {
      "maxDuration": 60,
      "memory": 1024,
      "excludeFiles": "{tests/**,openspec/**,.git/**,**/__pycache__/**,**/*.pyc,scripts/**}"
    }
  }
}
```

Rutas Workflow/step compiladas: `maxDuration: 800`, `memory: 3009` (4 GB Pro) por step en config de framework.

**Dependencias:** mantener pandas/openpyxl/pypdf/reportlab; excluir tests del bundle; monitorear tamaño (<500 MB).

## Compatibilidad Power Automate

- Rutas y métodos HTTP sin cambios.
- POST `/queue` → `{ job_id, status: "queued" }` en <5s.
- GET `/jobs/{job_id}` → `queued|running|completed|failed` + `user_message`, `next_action`, `severity` vía `enrich_job_for_http_response`.
- Tipos de job en `meta.type` unificados (incl. `validate_payment_report` si se migra el queue legacy).

## File Changes (plan)

| File | Action |
|------|--------|
| `vercel.json` | Create |
| `pyproject.toml` | Create (optional entrypoint + vercel scripts) |
| `app/domain/ports/job_store.py` | Create |
| `app/adapters/secondary/memory_job_store.py` | Create |
| `app/adapters/secondary/vercel_blob_job_store.py` | Create |
| `app/application/job_manager.py` | Modify → facade over JobStore |
| `app/adapters/primary/http/routers/payment_validation.py` | Modify → start workflow, remove BackgroundTasks |
| `app/adapters/primary/http/routers/sharepoint.py` | Modify → JobStore + workflows |
| `app/workflows/*.py` | Create (6 workflows + steps) |
| `requirements.txt` | Add `vercel` SDK |
| `.env.example` | Add `BLOB_READ_WRITE_TOKEN`, job TTL |

## Testing Strategy

| Layer | Qué | Cómo |
|-------|-----|------|
| Unit | JobStore, locks, result_ref | pytest + MemoryJobStore |
| Integration | Blob read/write | Vercel Blob test store |
| E2E | PA flows | staging Vercel + Graph sandbox |

## Migration / Rollout

Fases 1–8 (ver plan usuario). Criterio apagar Render: 7 días E2E verdes en Pro + sin jobs stuck + p95 GET job <2s.

## Open Questions

- [ ] API exacta Python SDK para `start_workflow` desde FastAPI (beta).
- [ ] Límite máximo Blob por objeto para `result.json`.
- [ ] Región única vs multi-región (Graph latency Ecuador/LATAM).
