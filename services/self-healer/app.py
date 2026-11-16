"""self-healer: recebe webhooks do Alertmanager e executa o equivalente a
`kubectl rollout restart deployment/<serviço>` para mitigar falhas sem
intervenção humana. Cooldown por deployment evita loops de restart."""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
log = logging.getLogger("self-healer")

TARGET_ALERT = "ToggleMasterHigh5xxRate"
ALLOWLIST = {
    "auth-service": "auth",
    "flag-service": "flag",
    "targeting-service": "targeting",
    "evaluation-service": "evaluation",
    "analytics-service": "analytics",
}
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "600"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


def emit(**fields):
    log.info(json.dumps({"event": "self_heal", **fields}, ensure_ascii=False))


def restart_deployment(name, namespace):
    """Mesmo patch que o `kubectl rollout restart` aplica."""
    from kubernetes import client, config

    config.load_incluster_config()
    now = datetime.now(timezone.utc).isoformat()
    body = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}}}}
    client.AppsV1Api().patch_namespaced_deployment(name=name, namespace=namespace, body=body)


def notify_discord(service, namespace, alert):
    if not DISCORD_WEBHOOK_URL:
        return
    summary = alert.get("annotations", {}).get("summary", "")
    content = (
        f"🤖 **Self-healing executado**: `kubectl rollout restart deployment/{service} -n {namespace}`\n"
        f"Alerta: `{alert.get('labels', {}).get('alertname')}` — {summary}\n"
        f"Próximo restart automático permitido em {COOLDOWN_SECONDS // 60} min."
    )
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=5)
    except requests.RequestException as e:
        emit(service=service, result="discord_error", error=str(e))


class Healer:
    def __init__(self, clock=time.monotonic):
        self.reset(clock)

    def reset(self, clock=time.monotonic):
        self.clock = clock
        self._last_restart = {}
        self._lock = threading.Lock()

    def handle(self, alert):
        labels = alert.get("labels", {})
        service = labels.get("service_name", "")
        relevant = alert.get("status") == "firing" and labels.get("alertname") == TARGET_ALERT
        if not relevant or service not in ALLOWLIST:
            emit(service=service, alertname=labels.get("alertname"), status=alert.get("status"), result="ignored")
            return {"service": service, "result": "ignored"}

        namespace = ALLOWLIST[service]
        with self._lock:
            last = self._last_restart.get(service)
            if last is not None and self.clock() - last < COOLDOWN_SECONDS:
                emit(service=service, result="cooldown", seconds_since_last=round(self.clock() - last))
                return {"service": service, "result": "cooldown"}
            self._last_restart[service] = self.clock()

        try:
            restart_deployment(service, namespace)
        except Exception as e:  # falha de API/RBAC: registra e libera o cooldown
            with self._lock:
                self._last_restart.pop(service, None)
            emit(service=service, namespace=namespace, result="error", error=str(e))
            return {"service": service, "result": "error"}

        emit(service=service, namespace=namespace, result="restarted",
             action=f"kubectl rollout restart deployment/{service} -n {namespace}")
        notify_discord(service, namespace, alert)
        return {"service": service, "result": "restarted"}


healer = Healer()
app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "self-healer"})


@app.route("/alert", methods=["POST"])
def alert_webhook():
    payload = request.get_json(silent=True) or {}
    actions = [healer.handle(a) for a in payload.get("alerts", [])]
    return jsonify({"actions": actions}), 200


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "8080")))
