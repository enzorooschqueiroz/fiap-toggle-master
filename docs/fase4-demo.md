# Roteiro do vídeo — Fase 4 (≤ 25 min)

Pré-gravação (fora do vídeo): `kubectl get applications -n argocd` tudo `Synced/Healthy`;
gerador de carga rodando há ≥ 10 min (dashboard com dados).

## Terminais/abas preparados

```bash
# T1 — port-forwards
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80 &
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
kubectl port-forward -n argocd svc/argocd-server 8080:443 &
kubectl port-forward -n flag svc/flag-service 8002:8002 &
kubectl port-forward -n evaluation svc/evaluation-service 8004:8004 &

# T2 — carga contínua (avaliações + chamadas diretas ao flag-service)
./scripts/load.sh

# T3 — observar pods do flag-service
kubectl get pods -n flag -w

# T4 — logs do self-healer
kubectl logs -n self-healing deploy/self-healer -f
```

Abas: ArgoCD (8080), Grafana (3000), New Relic (APM + Service Map), PagerDuty (Incidents), Discord (canal).

## 1. Visão geral — 3 min
- Diagrama da arquitetura (README, seção Fase 4).
- `kubectl get nodes` (EKS via Terraform) · `terraform -chdir=terraform output`.
- ArgoCD: apps `togglemaster`, `kube-prometheus-stack`, `loki`, `otel-collector` — tudo vindo do Git (`gitops/observability/`).

## 2. Métricas, logs e OTel — 6 min
- Grafana › dashboard **ToggleMaster — Saúde do Ecossistema**: recursos do cluster, req/s, % 5xx, p95, logs ao vivo.
- Explore › Loki: `{k8s_deployment_name="evaluation-service"} |= "Cache"`.
- Mostrar `gitops/observability/otel-collector.yaml`: receivers (OTLP + filelog) → processors (k8sattributes, batch) → exporters (Prometheus, Loki, New Relic).
- Mostrar instrumentação: `services/evaluation-service/main.go` (otelhttp, redisotel) e Dockerfile Python (`opentelemetry-instrument`).

## 3. APM e tracing — 5 min
- New Relic › APM & Services › **Service Map**: 5 serviços (analytics ligado via SQS).
- Requisição de teste:
  `curl "localhost:8004/evaluate?user_id=demo-$(date +%s)&flag_name=demo-flag"`
- Distributed tracing › trace do `GET /evaluate`: evaluation → Redis → flag → auth, targeting → auth, SQS send → analytics process.

## 4. Incidente e self-healing — 8 min
1. Injetar falha:
   ```bash
   curl -X POST localhost:8002/admin/chaos -H "Authorization: Bearer $MASTER_KEY" \
     -H "Content-Type: application/json" -d '{"error_rate": 100}'
   ```
2. Grafana: "% de erros HTTP 5xx" do flag-service sobe → após 2 min alerta **Firing** (painel de alertas / Alertmanager 9093).
3. PagerDuty: incidente aberto automaticamente.
4. Discord: notificação 🔥 FIRING com resumo, runbook e dashboard.
5. T4: log `{"event": "self_heal", "result": "restarted", ...}` · T3: pod novo do flag-service subindo.
6. Discord: mensagem "Self-healing executado".
7. Erros voltam a 0 (chaos era em memória) → alerta **RESOLVED** no Discord e no PagerDuty.

## 5. Fechamento — 1 min
- Feedback da Fase 3 aplicado (gates SCA/SAST bloqueantes, `k8s/` removido).
- Decisões: New Relic (OTLP nativo, free tier), PagerDuty (OpsGenie descontinuado).
