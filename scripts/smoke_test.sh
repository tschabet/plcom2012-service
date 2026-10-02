#!/usr/bin/env bash
# Smoke test against a running instance.
#   BASE_URL=https://plcom.example.org [API_KEY=...] scripts/smoke_test.sh
# Exit code is non-zero if any check fails. Needs only bash and curl.
set -u

BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
HERE="$(cd "$(dirname "$0")" && pwd)"
EXAMPLE="${EXAMPLE:-$HERE/../examples/questionnaire-response.json}"
OP="$BASE_URL/fhir/QuestionnaireResponse/\$plcom2012"
KEYHDR=()
[ -n "${API_KEY:-}" ] && KEYHDR=(-H "X-API-Key: $API_KEY")

fail=0
check() { # name, expected status, actual status, body, grep pattern ("" = none)
  local name="$1" want="$2" got="$3" body="$4" pat="$5"
  if [ "$got" = "$want" ] && { [ -z "$pat" ] || printf '%s' "$body" | grep -Eq "$pat"; }; then
    echo "ok    $name"
  else
    echo "FAIL  $name (HTTP $got, expected $want)"; printf '%s\n' "$body" | head -c 400; echo
    fail=1
  fi
}
call() { # prints "<status>\n<body>"
  curl -sS -m 15 -o /tmp/smoke_body.$$ -w '%{http_code}' "$@" ; echo; cat /tmp/smoke_body.$$; rm -f /tmp/smoke_body.$$
}
run() { # name want pattern -- curl args
  local name="$1" want="$2" pat="$3"; shift 4
  local out status body
  out="$(call "$@")"; status="$(printf '%s' "$out" | head -n1)"; body="$(printf '%s' "$out" | tail -n +2)"
  check "$name" "$want" "$status" "$body" "$pat"
}

echo "Target: $BASE_URL"
run "GET /health" 200 '"status": *"ok"' -- "$BASE_URL/health"
run "GET reference Questionnaire" 200 '"resourceType": *"Questionnaire"' -- "$BASE_URL/fhir/Questionnaire/plcom2012"
run "POST QuestionnaireResponse -> enriched QR" 200 'plcom2012-risk-percent' -- \
  -X POST "$OP" -H 'Content-Type: application/fhir+json' ${KEYHDR[@]+"${KEYHDR[@]}"} --data-binary "@$EXAMPLE"
run "POST ?output=observation -> Observation" 200 '"resourceType": *"Observation"' -- \
  -X POST "$OP?output=observation" -H 'Content-Type: application/fhir+json' ${KEYHDR[@]+"${KEYHDR[@]}"} --data-binary "@$EXAMPLE"
run "POST incomplete input -> 422 OperationOutcome" 422 'OperationOutcome' -- \
  -X POST "$OP" -H 'Content-Type: application/fhir+json' ${KEYHDR[@]+"${KEYHDR[@]}"} \
  --data-binary '{"resourceType":"QuestionnaireResponse","item":[]}'
run "POST wrong resource -> 400" 400 'OperationOutcome' -- \
  -X POST "$OP" -H 'Content-Type: application/fhir+json' ${KEYHDR[@]+"${KEYHDR[@]}"} --data-binary '{"resourceType":"Patient"}'
if [ -n "${API_KEY:-}" ]; then
  run "POST without API key -> 401" 401 'OperationOutcome' -- \
    -X POST "$OP" -H 'Content-Type: application/fhir+json' --data-binary "@$EXAMPLE"
fi

[ "$fail" = 0 ] && echo "ALL OK" || echo "FAILED"
exit "$fail"
