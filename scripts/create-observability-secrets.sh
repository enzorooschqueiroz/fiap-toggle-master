#!/usr/bin/env bash
# Cria/atualiza os Secrets da stack de observabilidade (nunca versionados no Git):
#   monitoring/newrelic-license        -> OTel Collector (exporter New Relic)
#   monitoring/grafana-admin           -> login do Grafana
#   monitoring/alertmanager-togglemaster -> rotas: PagerDuty + Discord + webhook do self-healer
#   self-healing/self-healer-discord   -> aviso do self-healer no Discord
#   flag/flag-service-secret (MASTER_KEY) -> protege POST /admin/chaos
# Uso: cp .env.observability.example .env.observability && ./scripts/create-observability-secrets.sh
set -euo pipefail

ENV_FILE="${1:-.env.observability}"
[[ -f "$ENV_FILE" ]] || { echo "Arquivo $ENV_FILE não encontrado (copie de .env.observability.example)"; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for v in NEW_RELIC_LICENSE_KEY PAGERDUTY_ROUTING_KEY DISCORD_WEBHOOK_URL GRAFANA_ADMIN_PASSWORD MASTER_KEY; do
  [[ -n "${!v:-}" ]] || { echo "Variável $v vazia em $ENV_FILE"; exit 1; }
done

apply_secret() { kubectl create secret generic "$@" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; }

kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl create namespace self-healing --dry-run=client -o yaml | kubectl apply -f - >/dev/null

apply_secret newrelic-license -n monitoring --from-literal=NEW_RELIC_LICENSE_KEY="$NEW_RELIC_LICENSE_KEY"
apply_secret grafana-admin -n monitoring \
  --from-literal=admin-user=admin --from-literal=admin-password="$GRAFANA_ADMIN_PASSWORD"
apply_secret self-healer-discord -n self-healing --from-literal=DISCORD_WEBHOOK_URL="$DISCORD_WEBHOOK_URL"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
render_alertmanager_config() {
  cat <<EOF
global:
  resolve_timeout: 5m
route:
  receiver: "null"
  group_by: [alertname, service_name]
  group_wait: 30s
  group_interval: 2m
  repeat_interval: 4h
  routes:
    - receiver: critical
      matchers: ['severity="critical"', 'alertname=~"ToggleMaster.*"']
    - receiver: warning
      matchers: ['severity="warning"', 'alertname=~"ToggleMaster.*"']
inhibit_rules:
  # Com 5xx crítico ativo, não notifica a latência do mesmo serviço (menos ruído)
  - source_matchers: ['severity="critical"']
    target_matchers: ['severity="warning"']
    equal: [service_name]
receivers:
  - name: "null"
  - name: critical
    pagerduty_configs:
      - routing_key: "${PAGERDUTY_ROUTING_KEY}"
        severity: critical
        send_resolved: true
        description: '{{ .CommonAnnotations.summary }}'
        client: ToggleMaster Alertmanager
        details:
          servico: '{{ .CommonLabels.service_name }}'
          descricao: '{{ .CommonAnnotations.description }}'
          runbook: '{{ .CommonAnnotations.runbook_url }}'
          self_healing: 'rollout restart automático solicitado ao self-healer'
    discord_configs:
      - webhook_url: "${DISCORD_WEBHOOK_URL}"
        send_resolved: true
        title: '{{ if eq .Status "firing" }}🔥 [FIRING]{{ else }}✅ [RESOLVED]{{ end }} {{ .CommonLabels.alertname }} — {{ .CommonLabels.service_name }}'
        message: |-
          {{ range .Alerts }}**Resumo:** {{ .Annotations.summary }}
          **Detalhes:** {{ .Annotations.description }}
          **Severidade:** {{ .Labels.severity }} | **Início:** {{ .StartsAt.Format "02/01 15:04:05 MST" }}
          **Runbook:** {{ .Annotations.runbook_url }}
          **Dashboard:** {{ .Annotations.dashboard_url }}
          {{ end }}📟 Incidente aberto no PagerDuty · 🤖 self-healing acionado
    webhook_configs:
      - url: http://self-healer.self-healing.svc.cluster.local:8080/alert
        send_resolved: true
  - name: warning
    discord_configs:
      - webhook_url: "${DISCORD_WEBHOOK_URL}"
        send_resolved: true
        title: '⚠️ [{{ .Status | toUpper }}] {{ .CommonLabels.alertname }} — {{ .CommonLabels.service_name }}'
        message: '{{ range .Alerts }}{{ .Annotations.summary }} — {{ .Annotations.runbook_url }}{{ end }}'
EOF
}
render_alertmanager_config > "$TMP/alertmanager.yaml"
apply_secret alertmanager-togglemaster -n monitoring --from-file=alertmanager.yaml="$TMP/alertmanager.yaml"

# MASTER_KEY no Secret do flag-service (endpoint de chaos); preserva as chaves existentes
if kubectl get secret flag-service-secret -n flag >/dev/null 2>&1; then
  kubectl patch secret flag-service-secret -n flag --type merge \
    -p "{\"stringData\":{\"MASTER_KEY\":\"${MASTER_KEY}\"}}" >/dev/null
else
  echo "Aviso: flag/flag-service-secret ainda não existe; rode scripts/create-service-secrets.sh antes."
fi

echo "Secrets de observabilidade aplicados."
