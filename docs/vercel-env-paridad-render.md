# Paridad de variables: Render → Vercel

Tras pruebas en producción (2026-05-26), **copiar todas las `GRAPH_*` de Render** al proyecto Vercel `automitizacion-hbi-capital`.

## Comprobar en producción

```http
GET https://automitizacion-hbi-capital.vercel.app/diagnostics/graph-env-present
```

Si `all_core_ok` es `false`, revisar `missing_core` y añadir esas variables en Vercel.

## Hallazgo notify

- **Render:** notify → `completed`
- **Vercel:** notify → `failed` — `Missing environment variable: GRAPH_SHAREPOINT_FILE_PATH`

## Variables núcleo (obligatorias)

- `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`
- `GRAPH_SHAREPOINT_SITE_SEARCH`, `GRAPH_SHAREPOINT_DRIVE_NAME`
- `GRAPH_SHAREPOINT_FILE_PATH`

## Generate / finalize

- `GRAPH_BANK_PAYMENTS_FILE_PATH`
- `GRAPH_CLIENTS_BASE_PATH`
- `GRAPH_PAYMENT_VALIDATION_REVIEW_PATH`
- `GRAPH_PAYMENT_VALIDATION_HISTORY_PATH`
- `GRAPH_VALIDATION_FILE_PREFIX`

## Merge / dry-run / notify

- `GRAPH_PAYMENT_VALIDATION_CONTROL_PATH`
- `GRAPH_PAYMENT_VALIDATION_LOGS_PATH`
- `GRAPH_MERGE_CONTROL_WORKBOOK_PATH`
- `GRAPH_VALIDAR_EXTRACTO_ESTADO_CONTAINS`
- `GRAPH_VALIDAR_NOTIFY_CORREOS_XLSX_PATH`

## Locks compartidos

Render y Vercel comparten **el mismo Blob** si usan el mismo `BLOB_READ_WRITE_TOKEN`. No ejecutar generate/finalize en ambos a la vez.

```http
POST /diagnostics/payment-validation/locks/release
```

## Script de comparación

```bash
python scripts/compare_render_vercel_prod.py --release-locks --poll-seconds 150
```
