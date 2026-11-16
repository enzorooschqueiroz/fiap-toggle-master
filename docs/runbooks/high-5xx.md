# Runbook — ToggleMasterHigh5xxRate

| | |
|---|---|
| **Severidade** | critical (pagina o PagerDuty) |
| **Condição** | `% de respostas 5xx > 5%` por 2 min em um serviço (com > 0,1 req/s) |
| **Fonte** | métrica OTel `http.server.request.duration` → OTel Collector → Prometheus |
| **Ação automática** | `self-healer` executa `kubectl rollout restart deployment/<serviço>` (cooldown 10 min) |

## Impacto

- **auth-service**: chaves não validam → flag e targeting respondem 401/503 → avaliação degrada.
- **flag-service / targeting-service**: cache MISS do evaluation falha → `/evaluate` responde 502.
- **evaluation-service**: clientes não recebem decisão de flag (caminho crítico).

## O que já aconteceu automaticamente

1. Alertmanager abriu incidente no PagerDuty e avisou no Discord.
2. O self-healer reiniciou o deployment (ver Discord: "Self-healing executado").

## Verificação (5 min)

```bash
# 1. O restart aconteceu?
kubectl logs -n self-healing deploy/self-healer | grep self_heal | tail
kubectl rollout history deployment/<serviço> -n <ns>

# 2. Pods novos saudáveis?
kubectl get pods -n <ns> -w

# 3. Taxa de erro caindo? Grafana > "ToggleMaster — Saúde do Ecossistema" > "% de erros HTTP 5xx"

# 4. Causa: logs e traces do período
#    Grafana > Explore > Loki: {k8s_deployment_name="<serviço>"} |~ "(?i)error"
#    New Relic > APM > <serviço> > Errors / Distributed tracing
```

## Se o restart não resolveu (alerta continua FIRING após 5 min)

O problema não é estado do processo — é dependência ou código:

| Sintoma no trace/log | Ação |
|---|---|
| Erro de conexão PostgreSQL | Checar RDS no console (status, conexões), Security Group |
| Timeout para `auth-service` | Seguir este runbook para o auth-service |
| Erro após deploy recente | `argocd app history togglemaster` → reverter o commit da tag no `gitops/` (GitOps rollback) |
| `[CHAOS] erro injetado` | Demo: `POST /admin/chaos {"error_rate":0}` ou aguardar o restart |

Novo restart automático só após o cooldown (10 min) — evita loop de restarts.
