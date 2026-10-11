"""Проверка живого стенда. Пробы — короткоживущие контейнеры в нужной сети: так тест видит
сеть так же, как её видят сервисы, а не с хоста."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any

import docker
import pytest
from docker.models.containers import Container

PROBE_IMAGE = "python:3.12-slim-bookworm"  # базовый образ сервиса — уже есть локально


@pytest.fixture(scope="session")
def client() -> Iterator[docker.DockerClient]:
    c = docker.from_env()
    yield c
    c.close()


@pytest.fixture(scope="session")
def prefix() -> str:
    return os.environ.get("STAND_PREFIX", "stand")


@pytest.fixture
def stand(client: docker.DockerClient, prefix: str) -> dict[str, Container]:
    names = {
        "nginx": f"{prefix}-nginx",
        "primary": f"{prefix}-db-primary",
        "replica": f"{prefix}-db-replica",
        "app1": f"{prefix}-app-1",
        "app2": f"{prefix}-app-2",
    }
    found = {}
    for key, name in names.items():
        try:
            found[key] = client.containers.get(name)
        except docker.errors.NotFound:
            pytest.skip(f"стенд не развёрнут: нет {name} (make infra deploy)")
    return found


def run_probe(client: docker.DockerClient, network: str, code: str, *args: str, timeout: int = 60) -> str:
    container = client.containers.run(PROBE_IMAGE, ["python", "-c", code, *args], network=network, detach=True)
    try:
        result = container.wait(timeout=timeout)
        output = container.logs(stdout=True, stderr=False).decode()
        if result["StatusCode"] != 0:
            raise AssertionError(f"проба упала: {container.logs().decode()}")
        return output
    finally:
        container.remove(force=True)


CONNECT = """
import json, socket, sys
results = {}
for target in json.loads(sys.argv[1]):
    name, host, port = target
    s = socket.socket()
    s.settimeout(2)
    try:
        results[name] = s.connect_ex((host, port)) == 0
    except OSError:
        results[name] = False  # имя не разрешается — тоже «недоступно»
    finally:
        s.close()
print(json.dumps(results))
"""


def reachability(client: docker.DockerClient, network: str, targets: list[tuple[str, str, int]]) -> dict[str, bool]:
    return json.loads(run_probe(client, network, CONNECT, json.dumps(targets)))  # type: ignore[no-any-return]


def ip_in(container: Container, network: str) -> str:
    container.reload()
    return container.attrs["NetworkSettings"]["Networks"][network]["IPAddress"]  # type: ignore[no-any-return]


def psql(container: Container, sql: str) -> tuple[int, str]:
    code, out = container.exec_run(["psql", "-U", "postgres", "-d", "orders", "-tAc", sql])
    return code, out.decode().strip()


def wait_for(fn: Any, timeout: float = 10.0, interval: float = 0.2) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = fn()
        if value or time.monotonic() > deadline:
            return value
        time.sleep(interval)
