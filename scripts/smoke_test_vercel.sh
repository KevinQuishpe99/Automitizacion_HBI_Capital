#!/usr/bin/env bash
# Smoke test de endpoints migrados a Vercel Workflow.
# Uso: bash scripts/smoke_test_vercel.sh [BASE_URL]
# Requiere: curl, jq

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
BASE_URL="${BASE_URL%/}"

echo "=== Smoke test Vercel Workflow ==="
echo "BASE_URL=$BASE_URL"
echo

fail() { echo "FAIL: $*" >&2; exit 1; }

assert_queued() {
  local body="$1"
  local job_id status http_code
  job_id=$(echo "$body" | jq -r '.job_id // empty')
  status=$(echo "$body" | jq -r '.status // empty')
  [[ -n "$job_id" ]] || fail "respuesta sin job_id: $body"
  [[ "$status" == "queued" ]] || fail "status esperado queued, got: $status"
  echo "$job_id"
}

poll_job() {
  local url="$1"
  local job_id="$2"
  local i
  for i in 1 2 3 4 5 6; do
    sleep 5
    local st
    st=$(curl -sS "$url" | jq -r '.status // empty')
    echo "  poll $i: status=$st"
    [[ "$st" == "completed" || "$st" == "failed" ]] && return 0
  done
  echo "  (timeout suave — revisar job manualmente)"
}

echo "--- Pre-check ---"
curl -sS -o /dev/null -w "health HTTP %{http_code}\n" "$BASE_URL/health"
curl -sS "$BASE_URL/diagnostics/runtime-config-safe" | jq .
echo

echo "--- Workflow ping ---"
PING_BODY=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL/diagnostics/workflow-ping/queue")
PING_HTTP=$(echo "$PING_BODY" | tail -n1)
PING_JSON=$(echo "$PING_BODY" | sed '$d')
[[ "$PING_HTTP" == "202" ]] || fail "workflow-ping HTTP $PING_HTTP"
PING_JOB=$(assert_queued "$PING_JSON")
poll_job "$BASE_URL/diagnostics/workflow-ping/jobs/$PING_JOB" "$PING_JOB"
echo

queue_post() {
  local name="$1"
  local path="$2"
  local data="${3:-}"
  local extra_curl=("${@:4}")
  echo "--- $name ---"
  local resp http json job
  if [[ -n "$data" ]]; then
    resp=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL$path" \
      -H "Content-Type: application/json" -d "$data" "${extra_curl[@]}")
  else
    resp=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL$path" "${extra_curl[@]}")
  fi
  http=$(echo "$resp" | tail -n1)
  json=$(echo "$resp" | sed '$d')
  [[ "$http" == "202" ]] || echo "WARN: HTTP $http (esperado 202) en $path"
  job=$(assert_queued "$json")
  echo "  job_id=$job"
  echo "$job"
}

# SharePoint validate-payment-report/queue puede responder 200 en algunas versiones
echo "--- validate-payment-report/queue ---"
VR=$(curl -sS -w "\n%{http_code}" -X POST "$BASE_URL/graph/sharepoint/validate-payment-report/queue")
VR_HTTP=$(echo "$VR" | tail -n1)
VR_JSON=$(echo "$VR" | sed '$d')
[[ "$VR_HTTP" == "202" || "$VR_HTTP" == "200" ]] || fail "validate-payment-report/queue HTTP $VR_HTTP"
VR_JOB=$(assert_queued "$VR_JSON")
echo "  job_id=$VR_JOB HTTP=$VR_HTTP"
echo

GEN_JOB=$(queue_post "payment-validation generate" "/graph/sharepoint/payment-validation/generate/queue" '{}')
poll_job "$BASE_URL/graph/sharepoint/payment-validation/jobs/$GEN_JOB" "$GEN_JOB"
echo

FIN_JOB=$(queue_post "payment-validation finalize" "/graph/sharepoint/payment-validation/finalize/queue" \
  '{"process_date":"2026-05-15"}')
poll_job "$BASE_URL/graph/sharepoint/payment-validation/jobs/$FIN_JOB" "$FIN_JOB"
echo

NOTIFY_JOB=$(queue_post "notify validar extractos" "/graph/sharepoint/notify-validar-extractos-email" \
  '{"historical_file_path":"test/path.xlsx"}')
curl -sS "$BASE_URL/graph/sharepoint/notify-validar-extractos-email/jobs/$NOTIFY_JOB" | jq -r '.status,.job_id' || true
echo

MERGE_JOB=$(queue_post "merge composite PDFs" "/graph/sharepoint/merge-composite-validado-pdfs" \
  '{"force_rebuild":false}')
curl -sS "$BASE_URL/graph/sharepoint/merge-composite-validado-pdfs/jobs/$MERGE_JOB" | jq -r '.status,.job_id' || true
echo

ENS_JOB=$(queue_post "ensure asientos" "/graph/sharepoint/ensure-asientos-contables-folders")
curl -sS "$BASE_URL/graph/sharepoint/ensure-asientos-contables-folders/jobs/$ENS_JOB" | jq -r '.status,.job_id' || true
echo

DRY_JOB=$(queue_post "amortization dry-run" \
  "/graph/sharepoint/payment-validation/amortization/dry-run/queue" \
  '{"report_date_iso":"2026-05-15"}')
poll_job "$BASE_URL/graph/sharepoint/payment-validation/jobs/$DRY_JOB" "$DRY_JOB"
echo

APPLY_JOB=$(queue_post "amortization apply" \
  "/graph/sharepoint/payment-validation/amortization/apply/queue" \
  '{"report_date_iso":"2026-05-15"}')
poll_job "$BASE_URL/graph/sharepoint/payment-validation/jobs/$APPLY_JOB" "$APPLY_JOB"
echo

echo "=== Smoke test encolado OK (revisar jobs failed por Graph/env) ==="
