# Fase 4 — Observabilidade, APM, Alertas e Self-Healing (design)

Data: 2026-11-15 · Autor: Enzo (com Claude)

## Intenção

Fechar o Tech Challenge (Fase 4, 90% da nota da fase) sobre a base das Fases 1–3
(5 microsserviços, Terraform, CI DevSecOps, ArgoCD). A banca só pontua o que
aparecer **funcionando** no vídeo (≤25 min) ou no relatório PDF — então cada
requisito precisa de uma demonstração reproduzível, não só de configuração.

## Objetivos

1. Prometheus + Loki + Grafana instalados **via GitOps** (ArgoCD), com 1 dashboard
   customizado: recursos do cluster, taxa de requisições por serviço, logs ao vivo.
2. **OTel Collector** como ponto central: recebe métricas/logs/traces e roteia para
   Prometheus, Loki e o APM.
3. Os 5 serviços instrumentados com OpenTelemetry; trace distribuído partindo do
   `evaluation-service`; Service Map com os 5 serviços no APM.
4. Alerta inteligente → incidente no PagerDuty + notificação no Discord.
5. Self-healing automático: alerta dispara `rollout restart` do deployment afetado.
6. Relatório PDF + roteiro do vídeo.

## Não-objetivos

- Alta disponibilidade/retenção longa da stack de observabilidade (é demo).
- Expor Grafana/Prometheus publicamente (acesso por `kubectl port-forward`).
- Reescrever lógica de negócio dos serviços.

## Anti-objetivos (seria fracasso mesmo "funcionando")

- Estourar os US$ 111 de crédito AWS (plano gratuito, vence 07/03/2027).
- Segredos (license key, routing key, webhook) commitados no Git.
- Self-healing em loop reiniciando pods sem parar (alert fatigue).
- `analytics-service` aparecer solto no Service Map (quebra da cadeia via SQS).

## Restrições

- Conta AWS no **plano gratuito**: tudo foi destruído; será recriado via Terraform.
  Estimativa ~US$ 0,40–0,45/h com tudo ligado (EKS 0,10 + 2 nós ~0,19 + NAT 0,045 +
  3×RDS micro + ElastiCache + EBS) ≈ US$ 10/dia → `terraform destroy` ao fim de cada
  sessão de trabalho longa.
- **Nós atuais (t3.small) não comportam a stack**: limite de 11 pods/nó e 2 GB RAM.
  Alvo: 2× `m7i-flex.large` (2 vCPU / 8 GB, 29 pods/nó, elegível ao plano gratuito)
  ou, se a conta não permitir, `t3.medium`. **Verificar no primeiro apply.**
- ArgoCD já sincroniza `gitops/` inteiro com `directory.recurse: true` (app-of-apps
  natural): novos `Application` em `gitops/` são aplicados automaticamente.
- Stack: Go 1.24 (auth, evaluation), Python 3.12/Flask/gunicorn (flag, targeting,
  analytics). Chamadas: evaluation → flag, targeting (HTTP); flag/targeting → auth
  (`/validate`); evaluation → SQS → analytics (assíncrono).

## Abordagens consideradas

| | Abordagem | Trade-off |
|---|---|---|
| A | Construir/testar local (k3d + LocalStack), subir EKS só para gravar | Mais barato, mas trabalho extra para imitar a AWS |
| **B** | **Trabalhar direto no EKS** | **Escolhida pelo Enzo.** Um ambiente só, fiel ao que será gravado; custo controlado com destroy entre sessões |

Ferramentas (escolhas do Claude, aceitas pelo Enzo):
- **APM: New Relic** — ingere OTLP nativo (Collector só exporta `otlphttp`), free
  tier permanente (100 GB/mês). Datadog exigiria exporter próprio e trial de 14 dias.
- **Incidentes: PagerDuty** — OpsGenie está sendo descontinuado pela Atlassian
  (sem novos cadastros).
- **ChatOps: Discord** — webhook simples, suporte nativo no Alertmanager.
- **Self-healing: receptor de webhook in-cluster** (vs. GitHub Action via
  `repository_dispatch`): sem credencial AWS exposta, latência baixa, RBAC mínimo.

## Design

### 1. Stack no cluster (GitOps)

Novos manifests em `gitops/observability/`, cada um um `Application` do ArgoCD
apontando para Helm chart público, com values inline:

- `kube-prometheus-stack` (namespace `monitoring`): Prometheus (com
  `enableRemoteWriteReceiver`), Alertmanager, Grafana, node-exporter,
  kube-state-metrics. Grafana com datasources Prometheus, Loki e Alertmanager e
  sidecar de dashboards (ConfigMaps com label `grafana_dashboard: "1"`).
- `loki` (single binary, storage filesystem em `emptyDir`; ingestão OTLP nativa do Loki 3).
- `opentelemetry-collector` (contrib) — ver §2.
- Dashboard "ToggleMaster — Saúde do Ecossistema" como ConfigMap JSON em Git:
  CPU/memória por nó e namespace, pods/restarts, req/s, p95 e % 5xx por serviço,
  painel de logs Loki ao vivo com variável `service`.

Storage: `emptyDir` em Prometheus e Loki (cluster sem EBS CSI driver; retenção não é objetivo — dados duram o ciclo de vida do pod, suficiente para a demo).

### 2. OTel Collector (peça central)

DaemonSet (um por nó), modo único para simplicidade:

- **Receivers:** `otlp` (gRPC 4317 / HTTP 4318) dos serviços; `filelog` em
  `/var/log/pods` para logs de **todos** os contêineres do cluster.
- **Processors:** `memory_limiter`, `k8sattributes` (namespace, pod, deployment),
  `resource` (`deployment.environment=dev`), `batch`.
- **Pipelines/exporters:**
  - traces → New Relic (`otlphttp`, endpoint `otlp.nr-data.net`, header `api-key`)
  - metrics → Prometheus (`prometheusremotewrite`) **e** New Relic
  - logs → Loki (`otlphttp` em `/otlp`) **e** New Relic (logs-in-context)

Infra (nós, kubelet, kube-state) continua sendo raspada pelo Prometheus direto;
métricas e traces de aplicação passam obrigatoriamente pelo Collector.

### 3. Instrumentação

Todos os deployments recebem `OTEL_SERVICE_NAME`,
`OTEL_EXPORTER_OTLP_ENDPOINT` (IP do nó via `status.hostIP`, porta 4317/4318) e
`OTEL_RESOURCE_ATTRIBUTES`.

- **Go (auth, evaluation):** SDK OTel + `otelhttp` no servidor e no `http.Client`
  (propaga `traceparent` para flag/targeting), `redisotel` no go-redis,
  spans manuais nas queries pgx (auth). Métricas HTTP via meter provider OTLP.
- **Python (flag, targeting, analytics):** zero-code —
  `opentelemetry-distro` + `opentelemetry-exporter-otlp` no `requirements.txt`,
  `opentelemetry-bootstrap -a install` no Dockerfile, CMD com
  `opentelemetry-instrument gunicorn ...` (Flask, requests, psycopg2, botocore,
  logging com trace_id).
- **Ponte SQS:** evaluation injeta o contexto W3C nos `MessageAttributes`;
  analytics extrai e cria o span `process` como filho → analytics aparece
  conectado no Service Map.
- **Injeção de falha para a demo:** endpoint `POST /admin/chaos` (protegido pela
  master key) em auth-service e flag-service que liga um modo in-memory de retornar
  500 em X% das requisições. Como é em memória, o `rollout restart` **realmente
  cura** — prova o self-healing de verdade. Alternativa de demo: derrubar o banco
  do flag-service (alerta + incidente funcionam, mas restart não cura).

CI existente continua igual (build → scan → ECR → bump de tag no GitOps).

### 4. Alertas, incidentes e self-healing

- `PrometheusRule` **ToggleMasterHigh5xxRate**: `% 5xx > 5%` por 2 min, por
  `service_name` (fonte: `http.server.request.duration` do OTel), severidade
  `critical`, com `runbook_url` e descrição. Mais um alerta `warning` de latência
  p95 (não pagina — só Discord), mostrando o cuidado com alert fatigue.
- **Alertmanager** roteia `critical` para três receivers:
  `pagerduty_configs` (Events API v2), `discord_configs` (mensagem detalhada:
  serviço, valor, runbook, link Grafana) e `webhook_configs` → self-healer.
  `group_wait`/`repeat_interval` ajustados para não spammar. Alerta "Firing"
  visível no Grafana (datasource Alertmanager) e no Prometheus.
- **self-healer** (`services/self-healer`, Python ~100 linhas, namespace
  `self-healing`): recebe o webhook, mapeia `service_name` → deployment/namespace
  por allowlist, aplica o patch `kubectl.kubernetes.io/restartedAt` (equivalente ao
  `rollout restart`), **cooldown de 10 min por deployment**, loga JSON (vai pro
  Loki) e posta no Discord "self-healing executado em X". ServiceAccount com
  `Role` só de `get/patch deployments` nos namespaces dos serviços. Imagem via
  CI + novo repo ECR no Terraform.

### 5. Segredos

Não vão para o Git: `scripts/create-observability-secrets.sh` lê um `.env` local
(gitignored) e cria os Secrets (NR license key, PagerDuty routing key, Discord
webhook). Mesma abordagem dos `secret.example` da Fase 3.

### 6. Entregáveis

- Código: `gitops/observability/`, instrumentação nos 5 serviços,
  `services/self-healer`, Terraform (nós maiores, versão EKS, ECR), README Fase 4.
- `docs/fase4-demo.md`: roteiro do vídeo com comandos (visão geral EKS/ArgoCD →
  Grafana/Loki/OTel → New Relic Service Map + trace → chaos → Firing → PagerDuty +
  Discord → pod reiniciando no terminal → recuperação).
- Relatório PDF (mesmo formato da Fase 3) com os 4 prints obrigatórios e a
  justificativa técnica (arquitetura OTel, New Relic vs Datadog, PagerDuty vs
  OpsGenie).

## Ordem de execução (resumo)

1. Contas: New Relic, PagerDuty, servidor/canal Discord (Enzo).
2. Código offline (sem custo): instrumentação, self-healer, manifests, dashboard,
   testado com `docker compose` + Collector local.
3. Terraform apply (nós maiores) → ArgoCD → validar tudo no EKS.
4. Gravação + prints → `terraform destroy`.

## Deixado para quem implementar

Versões exatas dos charts, layout do dashboard, nomes de métricas finais
(dependem da semconv emitida), tamanhos de PVC.

## Prazo e custo

- **Entrega: fim do dia 17/11/2026.** Ambiente AWS pode ficar ligado de 15/11 até
  18/11 (~74 h, estimativa US$ 37–40 de US$ 111,75 em créditos).
- EKS sobe para a versão mais nova em **suporte padrão** (1.31 está em suporte
  estendido = US$ 0,60/h); logs `audit` do control plane desligados.

## Em aberto (Enzo)

- Grupo ou individual; nomes/RMs no relatório ("423451" = RM?).
