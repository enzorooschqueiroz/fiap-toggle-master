#!/usr/bin/env python3
"""Gera gitops/observability/dashboard-togglemaster.yaml (ConfigMap lido pelo sidecar do Grafana).
Uso: python3 scripts/gen-dashboard.py"""
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
SVC = 'service_name=~"$service"'
APPS_NS = 'k8s_namespace_name=~"auth|flag|targeting|evaluation|analytics|self-healing"'
panels, _id = [], [0]


def nid():
    _id[0] += 1
    return _id[0]


def row(title, y):
    panels.append({"id": nid(), "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}})


def ts(title, exprs, x, y, w=12, h=8, unit="short", ds=PROM, desc=""):
    panels.append({
        "id": nid(), "type": "timeseries", "title": title, "description": desc, "datasource": ds,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10}}, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
        "targets": [{"refId": chr(65 + i), "datasource": ds, "expr": e, "legendFormat": lf}
                    for i, (e, lf) in enumerate(exprs)],
    })


def stat(title, expr, x, y, unit="short", thresholds=None, w=6):
    steps = thresholds or [{"color": "green", "value": None}]
    panels.append({
        "id": nid(), "type": "stat", "title": title, "datasource": PROM,
        "gridPos": {"h": 4, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}}},
        "options": {"colorMode": "background", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}},
        "targets": [{"refId": "A", "datasource": PROM, "expr": expr}],
    })


REQ = f'sum by (service_name) (rate(http_server_request_duration_seconds_count{{{SVC}}}[1m]))'
ERR = (f'sum by (service_name) (rate(http_server_request_duration_seconds_count{{{SVC}, http_response_status_code=~"5.."}}[1m]))'
       f' / sum by (service_name) (rate(http_server_request_duration_seconds_count{{{SVC}}}[1m]))')
P95 = (f'histogram_quantile(0.95, sum by (le, service_name) '
       f'(rate(http_server_request_duration_seconds_bucket{{{SVC}}}[5m])))')

# --- Visão geral
row("Visão geral", 0)
stat("Requisições/s (total)", f'sum(rate(http_server_request_duration_seconds_count{{{SVC}}}[1m]))', 0, 1, "reqps")
stat("Taxa de erro 5xx (total)",
     f'sum(rate(http_server_request_duration_seconds_count{{{SVC}, http_response_status_code=~"5.."}}[1m]))'
     f' / sum(rate(http_server_request_duration_seconds_count{{{SVC}}}[1m]))', 6, 1, "percentunit",
     [{"color": "green", "value": None}, {"color": "orange", "value": 0.01}, {"color": "red", "value": 0.05}])
stat("Alertas ToggleMaster disparando", 'count(ALERTS{alertstate="firing", alertname=~"ToggleMaster.*"}) or vector(0)',
     12, 1, "short", [{"color": "green", "value": None}, {"color": "red", "value": 1}])
stat("Pods reiniciados (30 min)",
     'sum(increase(kube_pod_container_status_restarts_total{namespace=~"auth|flag|targeting|evaluation|analytics"}[30m]))',
     18, 1, "short", [{"color": "green", "value": None}, {"color": "orange", "value": 1}])

# --- Microsserviços
row("Microsserviços (OpenTelemetry)", 5)
ts("Taxa de requisições por serviço", [(REQ, "{{service_name}}")], 0, 6, unit="reqps")
ts("% de erros HTTP 5xx por serviço", [(ERR, "{{service_name}}")], 12, 6, unit="percentunit",
   desc="Alerta ToggleMasterHigh5xxRate dispara acima de 5% por 2 min")
ts("Latência p95 por serviço", [(P95, "{{service_name}}")], 0, 14, unit="s")
ts("Requisições por status HTTP",
   [(f'sum by (service_name, http_response_status_code) (rate(http_server_request_duration_seconds_count{{{SVC}}}[1m]))',
     "{{service_name}} {{http_response_status_code}}")], 12, 14, unit="reqps")

# --- Cluster
row("Recursos do cluster (EKS)", 22)
ts("CPU por nó (%)", [('100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100', "{{instance}}")],
   0, 23, w=8, unit="percent")
ts("Memória por nó (%)", [('(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100', "{{instance}}")],
   8, 23, w=8, unit="percent")
ts("Pods em execução por namespace", [('sum by (namespace) (kube_pod_status_phase{phase="Running"})', "{{namespace}}")],
   16, 23, w=8)
ts("CPU por namespace (cores)",
   [('sum by (namespace) (rate(container_cpu_usage_seconds_total{container!=""}[2m]))', "{{namespace}}")], 0, 31)
ts("Memória por namespace",
   [('sum by (namespace) (container_memory_working_set_bytes{container!=""})', "{{namespace}}")], 12, 31, unit="bytes")

# --- Logs
row("Logs (Loki)", 39)
ts("Linhas de log com erro por deployment",
   [(f'sum by (k8s_deployment_name) (count_over_time({{{APPS_NS}}} |~ "(?i)error|erro|chaos|critical" [1m]))',
     "{{k8s_deployment_name}}")], 0, 40, w=24, h=7, ds=LOKI)
panels.append({
    "id": nid(), "type": "logs", "title": "Logs em tempo real — $service", "datasource": LOKI,
    "gridPos": {"h": 14, "w": 24, "x": 0, "y": 47},
    "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True},
    "targets": [{"refId": "A", "datasource": LOKI, "expr": '{k8s_deployment_name=~"$service"} |~ "$search"'}],
})

services = ["auth-service", "flag-service", "targeting-service", "evaluation-service", "analytics-service",
            "self-healer"]
dashboard = {
    "uid": "togglemaster-health", "title": "ToggleMaster — Saúde do Ecossistema",
    "tags": ["togglemaster", "fase4"], "timezone": "browser", "refresh": "10s", "schemaVersion": 39,
    "time": {"from": "now-30m", "to": "now"},
    "templating": {"list": [
        {"name": "service", "label": "Serviço", "type": "custom", "multi": True, "includeAll": True,
         "allValue": ".+", "query": ",".join(services),
         "current": {"text": "All", "value": "$__all"},
         "options": [{"text": s, "value": s, "selected": False} for s in services]},
        {"name": "search", "label": "Buscar nos logs", "type": "textbox", "query": "",
         "current": {"text": "", "value": ""}},
    ]},
    "panels": panels,
}

configmap = {
    "apiVersion": "v1", "kind": "ConfigMap",
    "metadata": {"name": "dashboard-togglemaster", "namespace": "monitoring",
                 "labels": {"grafana_dashboard": "1"}},
    "data": {"togglemaster-health.json": json.dumps(dashboard, ensure_ascii=False, indent=2)},
}
out = Path(__file__).resolve().parent.parent / "gitops/observability/dashboard-togglemaster.yaml"
out.write_text("# Gerado por scripts/gen-dashboard.py — não editar à mão\n" + json.dumps(configmap, ensure_ascii=False, indent=2) + "\n")
print(f"ok: {out} ({len(panels)} painéis)")
