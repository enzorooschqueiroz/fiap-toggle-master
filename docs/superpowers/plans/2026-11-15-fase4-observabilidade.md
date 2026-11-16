# Fase 4 — Observabilidade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrumentar o ToggleMaster com OpenTelemetry, subir Prometheus/Loki/Grafana/OTel Collector via ArgoCD no EKS, enviar traces ao New Relic, e fechar o ciclo alerta → PagerDuty + Discord → self-healing.

**Architecture:** Serviços exportam OTLP para um OTel Collector (DaemonSet) que roteia traces→New Relic, métricas→Prometheus (remote write)+NR, logs (OTLP + filelog de todos os pods)→Loki+NR. Alertmanager (kube-prometheus-stack) dispara PagerDuty, Discord e um webhook para o `self-healer` in-cluster, que faz `rollout restart` com cooldown.

**Tech Stack:** Go 1.24 (OTel SDK, otelhttp, otelsql, redisotel v8), Python 3.12 (opentelemetry-distro zero-code), Helm charts via ArgoCD (kube-prometheus-stack, loki, opentelemetry-collector), Terraform 1.17, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-15-fase4-observabilidade-design.md`

## Global Constraints

- Entrega: fim de 17/11/2026. Infra pode ficar ligada até 18/11; `terraform destroy` depois.
- Nunca commitar segredos: NR license key, PagerDuty routing key, Discord webhook vêm de `.env.observability` (gitignored) via `scripts/create-observability-secrets.sh`.
- Namespaces dos serviços: `auth`, `flag`, `targeting`, `evaluation`, `analytics`; nomes de deployment = `<x>-service`. Novos: `monitoring`, `self-healing`.
- `OTEL_SERVICE_NAME` = nome do deployment (`auth-service` …). Python: `OTEL_SEMCONV_STABILITY_OPT_IN=http` para todos emitirem `http.server.request.duration` com `http.response.status_code`.
- Collector exporter Prometheus com `resource_to_telemetry_conversion: enabled: true` → label `service_name` nas métricas.
- Métrica do alerta: `http_server_request_duration_seconds_count` (labels `service_name`, `http_response_status_code`).
- Storage de Prometheus/Loki: `emptyDir` (sem PVC).
- Chaos: `POST /admin/chaos` body `{"error_rate": <0-100>}`, protegido pela master key (header `Authorization: Bearer <MASTER_KEY>`); estado só em memória, default 0. Afeta todas as rotas exceto `/health` e `/admin/*`.
- Self-healer: allowlist fixa dos 5 serviços, cooldown 600 s por deployment, só atua em alertas `status=firing` com `alertname=ToggleMasterHigh5xxRate`.
- Go sem toolchain local: rodar testes com `docker run --rm -v "$PWD":/src -w /src golang:1.24 go test ./...`.
- Branch de trabalho: `fase-4`; merge em `master` só quando o EKS estiver pronto (ArgoCD sincroniza `master`).

## Review Focus

1. Requisição ao evaluation-service com cache HIT no Redis → ainda precisa gerar trace com span do Redis (não só HTTP). Teste em Task 3.
2. Mensagem SQS sem atributo `traceparent` (mensagens antigas na fila) → analytics processa normalmente, sem crash. Teste em Task 4.
3. Webhook do Alertmanager com `status=resolved` ou serviço fora da allowlist → self-healer não reinicia nada (responde 200). Teste em Task 6.
4. Dois disparos do mesmo alerta em < 10 min → só um restart. Teste em Task 6.
5. `/health` durante chaos 100% → continua 200 (senão liveness mata o pod e mascara o self-healing). Testes em Tasks 2 e 4.

---

### Task 1: Terraform — EKS atual, nós maiores, ECR do self-healer

**Files:**
- Modify: `terraform/modules/eks/main.tf` (version `"1.31"` linha 90; `enabled_cluster_log_types` linha 99; defaults de `node_instance_types`, `node_max_size`)
- Modify: `terraform/main.tf` (lista `repositories` do módulo ecr)

- [ ] **Step 1:** Descobrir a versão mais nova em suporte padrão: `aws eks describe-cluster-versions --region us-east-1 --query 'clusterVersions[?versionStatus==\`STANDARD_SUPPORT\`].clusterVersion'`; usar a maior.
- [ ] **Step 2:** Setar `version` para ela; `enabled_cluster_log_types = ["api", "authenticator"]`; `node_instance_types` default `["m7i-flex.large"]`, `node_desired_size = 2`, `node_max_size = 3`; adicionar `"togglemaster/self-healer"` aos repositórios ECR (mesmo prefixo dos demais).
- [ ] **Step 3:** `cd terraform && terraform fmt -check -recursive && terraform validate` → sem erros.
- [ ] **Step 4:** Commit `feat(terraform): EKS em suporte padrão, nós m7i-flex.large, ECR self-healer`.

(Apply acontece na Task 9.)

### Task 2: auth-service — OTel + chaos

**Files:**
- Create: `services/auth-service/telemetry.go`, `services/auth-service/chaos.go`, `services/auth-service/chaos_test.go`
- Modify: `services/auth-service/main.go`, `go.mod`/`go.sum`

**Interfaces:**
- Produces: `func setupTelemetry(ctx context.Context, serviceName string) (shutdown func(context.Context) error, err error)` — TracerProvider + MeterProvider OTLP gRPC (endpoint via env padrão `OTEL_EXPORTER_OTLP_ENDPOINT`), propagator `TraceContext+Baggage`. Mesmo arquivo é copiado em evaluation (Task 3).
- Produces: `type Chaos struct{...}`; `func (c *Chaos) Middleware(next http.Handler) http.Handler`; `func (c *Chaos) AdminHandler(w, r)`; `func (c *Chaos) SetRate(p int)`.

- [ ] **Step 1: Testes que falham** em `chaos_test.go`:
  - `TestChaosOffPassesThrough`: rate 0 → 200 em `/validate`.
  - `TestChaosFullFails`: `SetRate(100)` → 500 em `/validate`.
  - `TestChaosHealthExempt`: `SetRate(100)` → `/health` 200.
  - `TestChaosAdminSetsRate`: POST `/admin/chaos` `{"error_rate":100}` → 200 e próxima `/validate` → 500; body com 150 → 400.
- [ ] **Step 2:** `docker run ... go test ./...` → FAIL (símbolos indefinidos).
- [ ] **Step 3:** Implementar `chaos.go` (rate atômico, `rand.Intn(100) < rate`) e `telemetry.go`. Em `main.go`: chamar `setupTelemetry`, abrir DB com `otelsql.Open("pgx", url, otelsql.WithAttributes(semconv.DBSystemPostgreSQL))`, registrar `/admin/chaos` atrás de `masterKeyAuthMiddleware`, envolver o mux com `chaos.Middleware` e depois `otelhttp.NewHandler(mux, "auth-service")`; logs com `log.Printf` mantidos (vão para o Loki via filelog).
- [ ] **Step 4:** `go test ./... -race` → PASS; `go vet ./...` limpo.
- [ ] **Step 5:** Commit `feat(auth-service): instrumentação OTel e endpoint de chaos`.

### Task 3: evaluation-service — OTel, propagação HTTP/Redis/SQS

**Files:**
- Create: `services/evaluation-service/telemetry.go` (cópia da Task 2), `services/evaluation-service/propagation.go`, `services/evaluation-service/propagation_test.go`
- Modify: `main.go`, `handlers.go`, `evaluator.go`, `sqs.go`, `go.mod`

**Interfaces:**
- Produces: `type sqsAttrCarrier map[string]*sqs.MessageAttributeValue` implementando `propagation.TextMapCarrier`; `func injectTraceContext(ctx context.Context) map[string]*sqs.MessageAttributeValue`.
- Muda assinaturas: `getDecision(ctx, userID, flagName)`, `getCombinedFlagInfo(ctx, flagName)`, `fetchFlag(ctx, name)`, `fetchRule(ctx, name)`, `sendEvaluationEvent(ctx, userID, flagName, result)` — contexto vindo de `r.Context()`; requests com `http.NewRequestWithContext`.

- [ ] **Step 1: Testes que falham** em `propagation_test.go`:
  - `TestInjectAddsTraceparent`: com span ativo de um `sdktrace.NewTracerProvider()` e propagator TraceContext, `injectTraceContext(ctx)` contém chave `traceparent` com `DataType == "String"` e valor contendo o trace ID.
  - `TestInjectWithoutSpanIsEmpty`: ctx vazio → mapa sem `traceparent`.
  - `TestRedisHitCreatesSpan`: miniredis (`github.com/alicebob/miniredis/v2`) + `redisotel.NewTracingHook()` + `tracetest.NewSpanRecorder()`; após `Get` existe ≥1 span finalizado.
- [ ] **Step 2:** `go test ./...` → FAIL.
- [ ] **Step 3:** Implementar: `HttpClient` com `Transport: otelhttp.NewTransport(http.DefaultTransport)`; `rdb.AddHook(redisotel.NewTracingHook())` (`github.com/go-redis/redis/extra/redisotel/v8`); goroutine do SQS recebe `trace.ContextWithSpanContext(context.Background(), trace.SpanContextFromContext(r.Context()))` (não o ctx da request, que é cancelado) e cria span `toggle-events-queue send` kind Producer com `MessageAttributes: injectTraceContext(ctx)`; mux envolto em `otelhttp.NewHandler`.
- [ ] **Step 4:** `go test ./... -race` → PASS.
- [ ] **Step 5:** Commit `feat(evaluation-service): tracing distribuído HTTP, Redis e SQS`.

### Task 4: Serviços Python — zero-code OTel, chaos no flag, contexto SQS no analytics

**Files:**
- Modify: `services/{flag,targeting,analytics}-service/requirements.txt`, `Dockerfile`
- Modify: `services/flag-service/app.py`, `services/analytics-service/app.py`
- Create: `services/flag-service/test_chaos.py`, `services/analytics-service/test_trace_context.py`

**Interfaces:**
- Produces (analytics): `def extract_context(message: dict) -> opentelemetry.context.Context` — lê `message.get("MessageAttributes", {})`, monta `{k: v["StringValue"]}` e chama `propagate.extract`.

- [ ] **Step 1:** requirements: adicionar `opentelemetry-distro==0.49b2`, `opentelemetry-exporter-otlp==1.28.2` (ou par compatível mais novo — distro `0.Xb` casa com SDK `1.(X-21)`). Dockerfile builder: `RUN pip install --user -r requirements.txt && opentelemetry-bootstrap -a install` (com PATH ajustado); CMD: `["opentelemetry-instrument", "gunicorn", "app:app", "--bind", "0.0.0.0:<porta>"]`.
- [ ] **Step 2: Testes que falham:**
  - `test_chaos.py` (env `DATABASE_URL`, `AUTH_SERVICE_URL`, `MASTER_KEY` setados e `SimpleConnectionPool` mockado antes do import): `test_health_exempt_under_chaos` (rate 100 → `/health` 200), `test_chaos_requires_master_key` (sem header → 401), `test_chaos_makes_flags_fail` (rate 100 → `GET /flags` 500), `test_chaos_rejects_out_of_range` (150 → 400).
  - `test_trace_context.py` (boto3 clients mockados): `test_extract_with_traceparent` (atributo `traceparent` válido → `trace.get_current_span(ctx).get_span_context().trace_id` igual ao do header), `test_extract_without_attributes` (mensagem sem `MessageAttributes` → não lança, span context inválido), `test_process_message_without_attrs_still_saves` (put_item chamado uma vez).
- [ ] **Step 3:** `cd services/flag-service && python3 -m pytest -q` → FAIL.
- [ ] **Step 4:** Implementar chaos no flag-service: `before_request` que ignora `/health` e `/admin/`; rota `POST /admin/chaos` validando `Authorization == f"Bearer {MASTER_KEY}"` (nova env `MASTER_KEY`, vinda do secret). No analytics: `receive_message(..., MessageAttributeNames=["All"])`; `process_message` envolve o trabalho em `tracer.start_as_current_span("toggle-events-queue process", context=extract_context(message), kind=SpanKind.CONSUMER)`.
- [ ] **Step 5:** pytest nos dois serviços → PASS; `docker build` dos 3 serviços → OK.
- [ ] **Step 6:** Commit `feat(python-services): instrumentação OTel zero-code, chaos e contexto SQS`.

### Task 5: Manifests GitOps dos serviços — variáveis OTel

**Files:** Modify `gitops/{auth,flag,targeting,evaluation,analytics}-service/base.yaml`

- [ ] **Step 1:** Em cada Deployment adicionar env:
  ```yaml
  - name: NODE_IP
    valueFrom: { fieldRef: { fieldPath: status.hostIP } }
  - name: OTEL_SERVICE_NAME
    value: <x>-service
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: http://$(NODE_IP):4317
  - name: OTEL_EXPORTER_OTLP_PROTOCOL
    value: grpc
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: deployment.environment=dev,service.namespace=togglemaster
  ```
  Python: + `OTEL_SEMCONV_STABILITY_OPT_IN=http`, `OTEL_PYTHON_LOG_CORRELATION=true`, `OTEL_LOGS_EXPORTER=none` (logs vão pelo filelog). flag-service: `MASTER_KEY` via `secretKeyRef` do secret do flag (o script da Task 8 adiciona a chave).
- [ ] **Step 2:** `kubectl apply --dry-run=client -f gitops/<x>/base.yaml` para os 5 → OK.
- [ ] **Step 3:** Commit `feat(gitops): variáveis OpenTelemetry nos deployments`.

### Task 6: self-healer

**Files:**
- Create: `services/self-healer/{app.py,requirements.txt,Dockerfile,test_app.py}`
- Create: `gitops/self-healer/base.yaml` (Namespace, ServiceAccount, Role+RoleBinding em cada um dos 5 namespaces com `apps/deployments: get,patch`, Deployment, Service porta 8080)
- Modify: `.github/workflows/ci-python.yml` (matrix + paths incluem `self-healer`)

**Interfaces:**
- Produces: `POST /alert` (payload webhook v4 do Alertmanager) → `{"actions": [{"service": str, "result": "restarted"|"cooldown"|"ignored"}]}`; `GET /health`.
- `ALLOWLIST = {"auth-service": "auth", "flag-service": "flag", "targeting-service": "targeting", "evaluation-service": "evaluation", "analytics-service": "analytics"}`; `COOLDOWN_SECONDS` env, default 600; `DISCORD_WEBHOOK_URL` env opcional.
- `def restart_deployment(name: str, namespace: str) -> None` — `AppsV1Api().patch_namespaced_deployment` com `spec.template.metadata.annotations["kubectl.kubernetes.io/restartedAt"] = utc isoformat`.

- [ ] **Step 1: Testes que falham** (`restart_deployment` e `requests.post` mockados, clock injetável):
  - `test_firing_allowlisted_restarts` → 1 chamada `("flag-service","flag")`, result `restarted`.
  - `test_resolved_ignored`, `test_unknown_service_ignored`, `test_other_alertname_ignored` → 0 chamadas.
  - `test_cooldown_blocks_second_restart` → 2 POST em t e t+300 → 1 restart, segundo `cooldown`; em t+601 → restart.
  - `test_discord_notified_on_restart` → POST no webhook com nome do serviço no conteúdo.
- [ ] **Step 2:** `python3 -m pytest -q` → FAIL.
- [ ] **Step 3:** Implementar Flask + `kubernetes` client (`config.load_incluster_config()`), logs JSON por ação (`{"event":"self_heal","service":..,"result":..}`). Dockerfile igual ao padrão Python do repo, usuário não-root.
- [ ] **Step 4:** pytest → PASS; `kubectl apply --dry-run=client -f gitops/self-healer/base.yaml` → OK; `docker build` OK.
- [ ] **Step 5:** Commit `feat(self-healer): rollout restart automático via webhook do Alertmanager`.

### Task 7: Stack de observabilidade (ArgoCD Applications)

**Files:**
- Create: `gitops/observability/kube-prometheus-stack.yaml`, `loki.yaml`, `otel-collector.yaml` (Applications em `argocd`, destino `monitoring`, `CreateNamespace=true`, `ServerSideApply=true`, Helm values inline)
- Create: `gitops/observability/dashboard-togglemaster.yaml` (ConfigMap `grafana_dashboard: "1"`)
- Create: `gitops/observability/alert-rules.yaml` (PrometheusRule)

- [ ] **Step 1: kube-prometheus-stack** (repo `https://prometheus-community.github.io/helm-charts`, versão fixa mais recente): `prometheus.prometheusSpec.enableRemoteWriteReceiver: true`, `ruleSelectorNilUsesHelmValues: false`, `retention: 2d`, sem storageSpec; `alertmanager.alertmanagerSpec.useExistingSecret: true` + `configSecret: alertmanager-togglemaster` (criado na Task 8); Grafana `additionalDataSources` Loki (`http://loki.monitoring:3100`) e Alertmanager; `grafana.sidecar.dashboards.searchNamespace: ALL`; senha admin via secret existente `grafana-admin`.
- [ ] **Step 2: Loki** (repo `https://grafana.github.io/helm-charts`, chart `loki`): `deploymentMode: SingleBinary`, `singleBinary.replicas: 1`, `loki.auth_enabled: false`, `loki.storage.type: filesystem`, `loki.commonConfig.replication_factor: 1`, `loki.schemaConfig` tsdb v13, `loki.limits_config.allow_structured_metadata: true`, réplicas 0 para read/write/backend, `chunksCache.enabled: false`, `resultsCache.enabled: false`, `lokiCanary.enabled: false`, `test.enabled: false`, `singleBinary.persistence.enabled: false`.
- [ ] **Step 3: OTel Collector** (repo `https://open-telemetry.github.io/opentelemetry-helm-charts`, `image.repository: otel/opentelemetry-collector-contrib`, `mode: daemonset`, `presets.logsCollection.enabled: true`, `presets.kubernetesAttributes.enabled: true`, `ports.otlp.hostPort: 4317`, `ports.otlp-http.hostPort: 4318`), `extraEnvsFrom` secret `newrelic-license`. Config:
  - exporters: `otlphttp/newrelic` (`endpoint: https://otlp.nr-data.net`, header `api-key: ${env:NEW_RELIC_LICENSE_KEY}`), `prometheusremotewrite` (`endpoint: http://kube-prometheus-stack-prometheus.monitoring:9090/api/v1/write`, `resource_to_telemetry_conversion.enabled: true`), `otlphttp/loki` (`endpoint: http://loki.monitoring:3100/otlp`), `debug`.
  - pipelines: traces `[otlp]→[memory_limiter,k8sattributes,resource,batch]→[otlphttp/newrelic]`; metrics `[otlp]→…→[prometheusremotewrite,otlphttp/newrelic]`; logs `[otlp,filelog]→…→[otlphttp/loki,otlphttp/newrelic]`.
- [ ] **Step 4: Dashboard** "ToggleMaster — Saúde do Ecossistema" (uid `togglemaster-health`): linhas (a) Cluster: CPU% e memória% por nó (`node_cpu_seconds_total`, `node_memory_*`), CPU/mem por namespace (`container_cpu_usage_seconds_total`), restarts (`kube_pod_container_status_restarts_total`); (b) Serviços: req/s `sum by (service_name)(rate(http_server_request_duration_seconds_count[1m]))`, % 5xx, p95 `histogram_quantile(0.95, sum by (le,service_name)(rate(http_server_request_duration_seconds_bucket[5m])))`; (c) Logs: painel Loki `{k8s_namespace_name=~"auth|flag|targeting|evaluation|analytics"}` filtrado por variável `$service`; (d) painel Alert list.
- [ ] **Step 5: PrometheusRule** `togglemaster-alerts` (label `release: kube-prometheus-stack`):
  - `ToggleMasterHigh5xxRate`: `sum by (service_name)(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m])) / sum by (service_name)(rate(http_server_request_duration_seconds_count[1m])) > 0.05`, `for: 2m`, `severity: critical`, annotations `summary`, `description` com `{{ $value | humanizePercentage }}`, `runbook_url` → `docs/runbooks/high-5xx.md`.
  - `ToggleMasterHighLatencyP95`: p95 > 1s por 5m, `severity: warning`.
- [ ] **Step 6:** `helm template` de cada chart com os values extraídos → renderiza sem erro; `kubectl apply --dry-run=client` nos YAMLs não-Helm → OK.
- [ ] **Step 7:** Commit `feat(observability): Prometheus, Loki, Grafana e OTel Collector via ArgoCD`.

### Task 8: Segredos, Alertmanager config, runbook e README

**Files:**
- Create: `scripts/create-observability-secrets.sh`, `.env.observability.example`, `docs/runbooks/high-5xx.md`, `docs/fase4-demo.md`
- Modify: `.gitignore` (`.env.observability`), `README.md` (seção Fase 4 com diagrama do fluxo OTel)

- [ ] **Step 1:** Script (`set -euo pipefail`, falha se variável faltar) cria/atualiza via `kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -`: `monitoring/newrelic-license`, `monitoring/grafana-admin`, `monitoring/alertmanager-togglemaster` (renderiza `alertmanager.yaml` via heredoc: route `group_by: [alertname, service_name]`, `group_wait: 30s`, `repeat_interval: 4h`; rota `severity=critical` → receiver `critical` com `pagerduty_configs` (routing_key, `severity: critical`), `discord_configs` (webhook_url, title/message com serviço, valor, runbook, link Grafana) e `webhook_configs` → `http://self-healer.self-healing:8080/alert`, `send_resolved: true`; `severity=warning` → só Discord), `self-healing/self-healer-discord`, e adiciona `MASTER_KEY` ao secret do flag-service.
- [ ] **Step 2:** `bash -n` e `shellcheck` no script → limpo; render do `alertmanager.yaml` validado com `docker run --rm -v ...:/c prom/alertmanager amtool check-config /c/alertmanager.yaml` → SUCCESS.
- [ ] **Step 3:** Runbook (sintoma, impacto, ação automática, verificação manual) e `docs/fase4-demo.md` (roteiro do vídeo ≤25 min na ordem do enunciado, com os comandos exatos: port-forwards, curl de carga, `curl -X POST .../admin/chaos`, `kubectl get pods -n flag -w`).
- [ ] **Step 4:** Commit `docs: segredos de observabilidade, runbook, roteiro da demo e README Fase 4`.

### Task 9: Subir no EKS e validar ponta a ponta

Pré-requisito (Enzo): contas New Relic (license key INGEST), PagerDuty (serviço + integração Events API v2 → routing key), Discord (canal + webhook). Preencher `.env.observability`.

- [ ] **Step 1:** `./scripts/bootstrap-backend.sh` (se o bucket não existir) → `terraform apply` → `aws eks update-kubeconfig --name togglemaster-dev-eks` → `kubectl get nodes` mostra 2 nós `Ready` m7i-flex.large. Se a conta recusar o tipo, trocar para `t3.medium` (`node_desired_size=3`) e reaplicar.
- [ ] **Step 2:** Instalar ingress-nginx e ArgoCD conforme `docs/argocd-setup.md`; recriar secrets dos serviços (Fase 3) + `scripts/create-observability-secrets.sh`; push da branch `fase-4`, merge em `master`; CI publica imagens novas (incl. self-healer) e atualiza tags.
- [ ] **Step 3:** `kubectl get applications -n argocd` → todas `Synced/Healthy`; `kubectl get pods -A` sem CrashLoop.
- [ ] **Step 4: Verificar fluxos** (cada um = evidência):
  - Carga: loop de `curl /evaluate` por 5 min → dashboard mostra req/s dos 5 serviços e logs ao vivo; Loki `{k8s_namespace_name="evaluation"}` retorna linhas.
  - New Relic: Service Map com os 5 serviços conectados (analytics via SQS); um trace de `/evaluate` com spans evaluation→flag→auth, evaluation→targeting→auth, redis, SQS send → analytics process.
  - Incidente: `POST /admin/chaos {"error_rate":100}` no flag-service → em ~3 min alerta `Firing` no Grafana → incidente PagerDuty aberto → mensagem no Discord → log do self-healer `restarted` → `kubectl get pods -n flag -w` mostra pod novo → taxa 5xx volta a 0 → alerta resolve.
- [ ] **Step 5:** Corrigir o que falhar (nova iteração commit→CI→ArgoCD) até os três fluxos passarem.

### Task 10: Evidências, vídeo e relatório

- [ ] **Step 1:** Prints: dashboard Grafana, trace distribuído NR, Service Map, notificação Discord, incidente PagerDuty, log do self-healer + terminal com pod reiniciando, ArgoCD apps.
- [ ] **Step 2:** Gravação seguindo `docs/fase4-demo.md` (Enzo).
- [ ] **Step 3:** Relatório PDF no formato da Fase 3 (`../fase-3/Relatorio_Tech_Challenge_Fase3.docx` como base): nomes/RMs/usernames, links repo + vídeo, prints obrigatórios, justificativa técnica (arquitetura OTel, New Relic vs Datadog, PagerDuty vs OpsGenie). Salvar em `../fase-4/`.
- [ ] **Step 4:** Após entrega (até 18/11): `terraform destroy` e conferir no console que não sobrou NAT/EIP/LB/EBS.
