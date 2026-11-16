from unittest import mock

import pytest

import app as healer_app


def alert(service="flag-service", status="firing", alertname="ToggleMasterHigh5xxRate"):
    return {
        "version": "4",
        "status": status,
        "alerts": [{
            "status": status,
            "labels": {"alertname": alertname, "service_name": service, "severity": "critical"},
            "annotations": {"summary": "5xx alto"},
        }],
    }


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = FakeClock()
    healer_app.healer.reset(clock=clock)
    healer_app.app.testing = True
    with mock.patch.object(healer_app, "restart_deployment") as restart, \
         mock.patch.object(healer_app.requests, "post") as post:
        yield healer_app.app.test_client(), restart, post, clock


def results(resp):
    return [a["result"] for a in resp.get_json()["actions"]]


def test_firing_allowlisted_restarts(env):
    client, restart, _, _ = env
    resp = client.post("/alert", json=alert())
    assert resp.status_code == 200
    restart.assert_called_once_with("flag-service", "flag")
    assert results(resp) == ["restarted"]


def test_resolved_ignored(env):
    client, restart, _, _ = env
    resp = client.post("/alert", json=alert(status="resolved"))
    assert resp.status_code == 200
    restart.assert_not_called()
    assert results(resp) == ["ignored"]


def test_unknown_service_ignored(env):
    client, restart, _, _ = env
    resp = client.post("/alert", json=alert(service="kube-dns"))
    assert resp.status_code == 200
    restart.assert_not_called()


def test_other_alertname_ignored(env):
    client, restart, _, _ = env
    resp = client.post("/alert", json=alert(alertname="ToggleMasterHighLatencyP95"))
    assert resp.status_code == 200
    restart.assert_not_called()


def test_cooldown_blocks_second_restart(env):
    client, restart, _, clock = env
    client.post("/alert", json=alert())
    clock.now += 300
    assert results(client.post("/alert", json=alert())) == ["cooldown"]
    assert restart.call_count == 1
    clock.now += 301
    assert results(client.post("/alert", json=alert())) == ["restarted"]
    assert restart.call_count == 2


def test_discord_notified_on_restart(env, monkeypatch):
    client, _, post, _ = env
    monkeypatch.setattr(healer_app, "DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    client.post("/alert", json=alert())
    post.assert_called_once()
    assert "flag-service" in post.call_args.kwargs["json"]["content"]


def test_restart_failure_reports_error(env):
    client, restart, _, _ = env
    restart.side_effect = RuntimeError("forbidden")
    resp = client.post("/alert", json=alert())
    assert resp.status_code == 200
    assert results(resp) == ["error"]


def test_health(env):
    client, _, _, _ = env
    assert client.get("/health").status_code == 200
