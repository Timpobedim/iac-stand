"""Живой стенд: сегментация сети, порты, права, репликация, сервис через nginx."""

from __future__ import annotations

import json

import docker
import pytest
from docker.models.containers import Container

from .conftest import ip_in, psql, reachability, run_probe, wait_for

HTTP = """
import json, sys, urllib.request
out = []
for path in json.loads(sys.argv[1]):
    method, url, body = path
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            out.append([r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()])
    except urllib.error.HTTPError as e:
        out.append([e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()])
print(json.dumps(out))
"""


def http(client: docker.DockerClient, prefix: str, *requests: tuple[str, str, object]) -> list[list[object]]:
    calls = [[m, f"http://nginx:8080{p}", b] for m, p, b in requests]
    return json.loads(run_probe(client, f"{prefix}-edge", HTTP, json.dumps(calls)))  # type: ignore[no-any-return]


# ------------------------------------------------------------------ сеть


def test_network_segmentation(client: docker.DockerClient, prefix: str, stand: dict[str, Container]) -> None:
    """Кто кого видит. Ожидание записано целиком: и разрешённые связи, и запрещённые."""
    primary_ip = ip_in(stand["primary"], f"{prefix}-db")
    app_ip = ip_in(stand["app1"], f"{prefix}-app")
    targets = [
        ("nginx", f"{prefix}-nginx", 8080),
        ("app", f"{prefix}-app-1", 8000),
        ("primary", f"{prefix}-db-primary", 5432),
        ("replica", f"{prefix}-db-replica", 5432),
        ("primary_by_ip", primary_ip, 5432),  # по адресу — сегменты разделены, а не только «имя не найдено»
        ("app_by_ip", app_ip, 8000),
        ("internet", "1.1.1.1", 443),
    ]
    expected = {
        "edge": {
            "nginx": True,
            "app": False,
            "primary": False,
            "replica": False,
            "primary_by_ip": False,
            "app_by_ip": False,
        },
        "app": {
            "nginx": True,
            "app": True,
            "primary": False,
            "replica": False,
            "primary_by_ip": False,
            "app_by_ip": True,
            "internet": False,
        },
        # Из сегмента баз виден сервис: сети Docker делят на сегменты, но не задают направление.
        "db": {"nginx": False, "app": True, "primary": True, "replica": True, "primary_by_ip": True, "internet": False},
    }
    actual = {}
    for segment, want in expected.items():
        seen = reachability(client, f"{prefix}-{segment}", targets)
        actual[segment] = {name: seen[name] for name in want}
    assert actual == expected


def test_only_nginx_published_on_loopback(
    client: docker.DockerClient, prefix: str, stand: dict[str, Container]
) -> None:
    published = {}
    for c in client.containers.list(all=True):
        if not c.name.startswith(f"{prefix}-"):
            continue
        bindings = c.attrs["HostConfig"].get("PortBindings") or {}
        if bindings:
            published[c.name] = sorted({b["HostIp"] for binds in bindings.values() for b in binds or []})
    assert published == {f"{prefix}-nginx": ["127.0.0.1"]}


# ------------------------------------------------------------------ права


def test_app_hardening(stand: dict[str, Container]) -> None:
    for key in ("app1", "app2"):
        c = stand[key]
        c.reload()
        assert c.attrs["Config"]["User"] == "10001"
        assert c.attrs["HostConfig"]["ReadonlyRootfs"] is True
        assert c.attrs["HostConfig"]["Memory"] == 256 * 1024 * 1024
        assert c.attrs["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"


def test_nginx_not_root(stand: dict[str, Container]) -> None:
    code, out = stand["nginx"].exec_run(["id", "-u"])
    assert code == 0
    assert out.decode().strip() == "101"


def test_superuser_cannot_connect_over_network(stand: dict[str, Container]) -> None:
    code, out = stand["app1"].exec_run(
        [
            "python",
            "-c",
            (
                "import psycopg\n"
                "try:\n"
                "    psycopg.connect('postgresql://postgres:guess@db-primary:5432/orders', connect_timeout=3)\n"
                "except psycopg.OperationalError as e:\n"
                "    print(e)\n"
            ),
        ]
    )
    assert code == 0
    assert "pg_hba.conf rejects connection" in out.decode()


# ------------------------------------------------------------------ репликация


def test_replication_streaming_with_slot(stand: dict[str, Container]) -> None:
    code, out = psql(stand["primary"], "SELECT state || ' ' || sync_state FROM pg_stat_replication")
    assert (code, out) == (0, "streaming async")
    code, out = psql(stand["primary"], "SELECT slot_name || ' ' || active FROM pg_replication_slots")
    assert (code, out) == (0, "replica_1 true")


def test_write_through_api_appears_on_replica(
    client: docker.DockerClient, prefix: str, stand: dict[str, Container]
) -> None:
    ((status, _, body),) = http(client, prefix, ("POST", "/orders", {"item": "проверка репликации", "qty": 3}))
    assert status == 201
    order_id = json.loads(body)["id"]
    found = wait_for(lambda: psql(stand["replica"], f"SELECT item FROM orders WHERE id = {order_id}")[1])
    assert found == "проверка репликации"


def test_replica_is_read_only(stand: dict[str, Container]) -> None:
    code, out = psql(stand["replica"], "INSERT INTO orders (item, qty) VALUES ('x', 1)")
    assert code != 0
    assert "read-only transaction" in out or code != 0


def test_service_role_cannot_delete(stand: dict[str, Container]) -> None:
    _code, out = stand["primary"].exec_run(
        [
            "psql",
            "-U",
            "postgres",
            "-d",
            "orders",
            "-tAc",
            "SELECT has_table_privilege('app', 'orders', 'DELETE'), has_table_privilege('app', 'orders', 'INSERT')",
        ]
    )
    assert out.decode().strip() == "f|t"


# ------------------------------------------------------------------ сервис


def test_health_and_both_instances_serve(client: docker.DockerClient, prefix: str) -> None:
    responses = http(client, prefix, *[("GET", "/health", None)] * 8)
    assert {r[0] for r in responses} == {200}
    upstreams = {r[1].get("x-upstream") for r in responses}
    assert len(upstreams) == 2, f"балансировка идёт не на два экземпляра: {upstreams}"


def test_order_read_back(client: docker.DockerClient, prefix: str) -> None:
    ((status, _, body),) = http(client, prefix, ("POST", "/orders", {"item": "болт", "qty": 2}))
    order_id = json.loads(body)["id"]
    ((status, headers, body),) = http(client, prefix, ("GET", f"/orders/{order_id}", None))
    assert status == 200
    assert json.loads(body)["item"] == "болт"
    assert headers["x-read-from"] in ("replica", "primary")


def test_replication_endpoint(client: docker.DockerClient, prefix: str) -> None:
    ((status, _, body),) = http(client, prefix, ("GET", "/replication", None))
    assert status == 200
    assert [r["state"] for r in json.loads(body)] == ["streaming"]


@pytest.mark.parametrize("path", ["/orders/abc", "/nope"])
def test_errors_do_not_leak_server_banner(client: docker.DockerClient, prefix: str, path: str) -> None:
    ((status, headers, _),) = http(client, prefix, ("GET", path, None))
    assert status in (404, 422)
    assert "nginx/" not in headers.get("server", "")
