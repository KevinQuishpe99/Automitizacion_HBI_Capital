# Migración de endpoints pesados a Vercel Workflow

Todos los endpoints `/queue` y `202` pesados usan `get_job_runner()`:

- `JOB_RUNNER_BACKEND=background` → FastAPI `BackgroundTasks` (Render/local)
- `JOB_RUNNER_BACKEND=vercel_workflow` + `VERCEL_WORKFLOWS_ENABLED=true` → Vercel Workflow + fallback API

## Endpoints migrados a workflow

| Endpoint | Workflow | Job |
|----------|----------|-----|
| `POST .../validate-payment-report/queue` | `validate_payment_report_workflow` | `validate_payment_report_job` |
| `POST .../notify-validar-extractos-email` | `notify_validar_extractos_workflow` | `notify_validar_extractos_job` |
| `POST .../merge-composite-validado-pdfs` | `merge_composite_validado_pdfs_workflow` | `merge_composite_validado_pdfs_job` |
| `POST .../ensure-asientos-contables-folders` | `ensure_asientos_contables_workflow` | `ensure_asientos_contables_job` |
| `POST .../payment-validation/generate/queue` | `payment_validation_generate_workflow` | `payment_validation_generate_job` |
| `POST .../payment-validation/finalize/queue` | `payment_validation_finalize_workflow` | `payment_validation_finalize_job` |
| `POST .../amortization/dry-run/queue` | (ya existía) | `amortization_dry_run_job` |
| `POST .../amortization/apply/queue` | (ya existía) | `amortization_apply_job` |

Los payloads solo envían referencias (paths SharePoint, fechas ISO, flags), no archivos grandes en el body HTTP.

## Semántica de `completed` y guardrails de observabilidad

En estos flujos de SharePoint (Vercel Workflow y fallback), `status=completed` significa que el job terminó, pero no garantiza que se haya generado/escrito un artefacto nuevo.

- `merge-composite-validado-pdfs`
  - Puede reutilizar un PDF consolidado existente cuando `result.already_consolidated=true` y todos los `outputs[*].bytes_written=0`.
  - En ese caso el `GET .../jobs/{job_id}` devuelve `severity='warning'` y recomienda usar `force_rebuild=true` para regenerar/reemplazar.
- `notify-validar-extractos-email`
  - Puede enviar el correo pero quedar `merge_control_updated=false` (no se actualizó el `control_merge_pdfs.xlsx` para el paso de unir PDFs).
  - El `GET .../jobs/{job_id}` devuelve `severity='warning'` para que se deje el control listo antes del siguiente paso.
- `payment-validation/finalize/queue`
  - Finalize puede reemplazar el histórico y el soporte del día. Si ya existían, el job reporta `warning_code='FINALIZE_OUTPUT_ALREADY_EXISTS'` y muestra `severity='warning'`.
- `payment-validation/amortization/apply/queue`
  - Puede terminar sin subir/escribir tablas cuando todo fue idempotente (`apply_wrote_changes=false`); el `GET .../jobs/{job_id}` marca `severity='warning'` con la señal clara.

## Endpoints que permanecen síncronos

- `GET /health`, `GET .../jobs/{job_id}` (consulta estado)
- Graph/SharePoint lecturas rápidas (`/site`, `/drives`, `/resolve-env`, etc.)
- `POST /parse-excel`, `POST /validate-excel`
- `POST .../validate-payment-report` (legacy síncrono, compatibilidad PA)
- `POST .../setup/*-workbook` (idempotentes, respuesta inmediata)
