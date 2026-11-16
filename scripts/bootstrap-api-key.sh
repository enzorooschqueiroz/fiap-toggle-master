#!/usr/bin/env bash
# Gera uma API key no auth-service (via port-forward) e grava em
# evaluation/evaluation-service-secret (SERVICE_API_KEY), reiniciando o evaluation.
# Uso: ./scripts/bootstrap-api-key.sh [.env.observability]
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env.observability}"
MASTER_KEY=$(grep -E '^MASTER_KEY=' "$ENV_FILE" | cut -d= -f2-)

kubectl port-forward -n auth svc/auth-service 18001:8001 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for _ in $(seq 1 20); do curl -sf localhost:18001/health >/dev/null && break; sleep 1; done

KEY=$(curl -sf -X POST localhost:18001/admin/keys \
  -H "Authorization: Bearer ${MASTER_KEY}" -H "Content-Type: application/json" \
  -d '{"name": "evaluation-service"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])')

kubectl patch secret evaluation-service-secret -n evaluation --type merge \
  -p "{\"stringData\":{\"SERVICE_API_KEY\":\"${KEY}\"}}" >/dev/null
kubectl rollout restart deployment/evaluation-service -n evaluation >/dev/null
echo "SERVICE_API_KEY gravada e evaluation-service reiniciado."
echo "Guarde para testes manuais: ${KEY}"
