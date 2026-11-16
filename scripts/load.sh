#!/usr/bin/env bash
# Gera tráfego contínuo para os dashboards/traces: avaliações no evaluation-service
# e leituras diretas no flag-service (necessárias para o alerta de 5xx do flag).
# Requer port-forwards: evaluation 8004, flag 8002. Uso: ./scripts/load.sh [flag_name]
set -uo pipefail
FLAG="${1:-demo-flag}"
KEY="${SERVICE_API_KEY:?exporte SERVICE_API_KEY (saída do bootstrap-api-key.sh)}"
i=0
while true; do
  i=$((i + 1))
  curl -s -o /dev/null -w "eval %{http_code}  " "localhost:8004/evaluate?user_id=user-$((i % 500))&flag_name=${FLAG}"
  curl -s -o /dev/null -w "flag %{http_code}\n" -H "Authorization: Bearer ${KEY}" "localhost:8002/flags/${FLAG}"
  sleep 0.3
done
