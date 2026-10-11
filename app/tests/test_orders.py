"""Сервис заказов без базы: поведение на отказах и при отставании реплики."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from orders.main import create_app


class FakeDb:
    def __init__(self) -> None:
        self.up = {"primary": True, "replica": True}
        self.recovery = True
        self.rows: dict[str, dict[int, dict[str, Any]]] = {"primary": {}, "replica": {}}
        self.lagging = False

    def ping(self, which: str) -> bool:
        return self.up[which]

    def in_recovery(self, which: str) -> bool:
        return self.recovery

    def insert_order(self, item: str, qty: int) -> dict[str, Any]:
        order = {"id": len(self.rows["primary"]) + 1, "item": item, "qty": qty, "created_at": "now"}
        self.rows["primary"][order["id"]] = order
        if not self.lagging:
            self.rows["replica"][order["id"]] = order
        return order

    def get_order(self, which: str, order_id: int) -> dict[str, Any] | None:
        return self.rows[which].get(order_id)

    def list_orders(self, limit: int) -> list[dict[str, Any]]:
        return list(self.rows["replica"].values())[-limit:]

    def replication(self) -> list[dict[str, Any]]:
        return [{"application_name": "replica", "state": "streaming", "sync_state": "async", "replay_lag_seconds": 0.0}]


@pytest.fixture
def db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def http(db: FakeDb) -> TestClient:
    return TestClient(create_app(db, "42"))


def test_health_ok(http: TestClient) -> None:
    response = http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"version": "42", "primary": "ok", "replica": "ok"}


@pytest.mark.parametrize(("which", "field"), [("primary", "primary"), ("replica", "replica")])
def test_health_fails_when_database_down(http: TestClient, db: FakeDb, which: str, field: str) -> None:
    db.up[which] = False
    response = http.get("/health")
    assert response.status_code == 503
    assert response.json()[field] == "unavailable"


def test_health_fails_when_replica_is_not_standby(http: TestClient, db: FakeDb) -> None:
    """Реплику по ошибке подняли как самостоятельную базу: запись пойдёт мимо репликации."""
    db.recovery = False
    response = http.get("/health")
    assert response.status_code == 503
    assert response.json()["replica"] == "not a standby"


def test_order_read_from_replica(http: TestClient) -> None:
    created = http.post("/orders", json={"item": "болт М8", "qty": 10}).json()
    response = http.get(f"/orders/{created['id']}")
    assert response.headers["X-Read-From"] == "replica"
    assert response.json()["item"] == "болт М8"


def test_lagging_replica_falls_back_to_primary(http: TestClient, db: FakeDb) -> None:
    db.lagging = True
    created = http.post("/orders", json={"item": "гайка", "qty": 1}).json()
    response = http.get(f"/orders/{created['id']}")
    assert response.status_code == 200
    assert response.headers["X-Read-From"] == "primary"


def test_missing_order_404(http: TestClient) -> None:
    assert http.get("/orders/999").status_code == 404


@pytest.mark.parametrize(
    "body", [{"item": "", "qty": 1}, {"item": "x", "qty": 0}, {"item": "x", "qty": 1001}, {"item": "x"}]
)
def test_order_validation(http: TestClient, body: dict[str, Any]) -> None:
    assert http.post("/orders", json=body).status_code == 422


def test_list_limit_clamped(http: TestClient) -> None:
    for i in range(3):
        http.post("/orders", json={"item": f"x{i}", "qty": 1})
    assert len(http.get("/orders?limit=0").json()) == 1
    assert len(http.get("/orders?limit=500").json()) == 3


def test_version_and_replication(http: TestClient) -> None:
    assert http.get("/version").json() == {"version": "42"}
    assert http.get("/replication").json()[0]["state"] == "streaming"
