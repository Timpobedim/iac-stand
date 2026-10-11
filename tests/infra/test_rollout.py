"""Выкат без простоя и откат неудачного релиза — на живом стенде.

Проба в сети edge непрерывно спрашивает /version, пока Ansible меняет экземпляры.
Оба теста оставляют стенд на той же версии, что была до них.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import docker
from docker.models.containers import Container

from .conftest import PROBE_IMAGE

ROOT = Path(__file__).resolve().parents[2]

LOOP = """
import time, urllib.request, urllib.error
while True:
    try:
        with urllib.request.urlopen("http://nginx:8080/version", timeout=3) as r:
            print(r.status, r.read().decode(), flush=True)
    except urllib.error.HTTPError as e:
        print(e.code, "-", flush=True)
    except Exception as e:
        print(0, type(e).__name__, flush=True)
    time.sleep(0.05)
"""


def current_version(stand: dict[str, Container]) -> str:
    stand["app1"].reload()
    return stand["app1"].attrs["Config"]["Image"].split(":")[-1]  # type: ignore[no-any-return]


def deploy_under_load(client: docker.DockerClient, prefix: str, *extra: str) -> tuple[int, list[tuple[int, str]]]:
    probe = client.containers.run(PROBE_IMAGE, ["python", "-c", LOOP], network=f"{prefix}-edge", detach=True)
    try:
        result = subprocess.run(
            ["ansible-playbook", "-i", "inventory/terraform.py", "deploy.yml", *extra],
            cwd=ROOT / "ansible",
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    finally:
        probe.stop(timeout=1)
        lines = probe.logs(stdout=True, stderr=False).decode().splitlines()
        probe.remove(force=True)
    answers = []
    for line in lines:
        code, _, body = line.partition(" ")
        answers.append((int(code), body))
    return result.returncode, answers


def test_redeploy_without_downtime(client: docker.DockerClient, prefix: str, stand: dict[str, Container]) -> None:
    version = current_version(stand)
    code, answers = deploy_under_load(client, prefix, "-e", f"app_version={version}")
    assert code == 0
    assert len(answers) > 50, "проба почти не успела спросить — проверка ничего не значит"
    failed = [a for a in answers if a[0] != 200]
    assert failed == [], f"{len(failed)} из {len(answers)} запросов во время выката без ответа 200"


def test_bad_release_rolls_back(client: docker.DockerClient, prefix: str, stand: dict[str, Container]) -> None:
    version = current_version(stand)
    code, answers = deploy_under_load(client, prefix, "-e", f"app_version={version}", "-e", "bad_release=true")
    assert code != 0, "релиз с неверным паролем базы не должен считаться успешным"
    assert [a for a in answers if a[0] != 200] == [], "во время неудачного релиза сервис отвечал ошибками"
    assert {json.loads(body)["version"] for _, body in answers} == {version}
    # Откат пересоздаёт контейнеры — берём их заново по имени.
    for n in (1, 2):
        container = client.containers.get(f"{prefix}-app-{n}")
        assert container.attrs["State"]["Health"]["Status"] == "healthy"
        assert container.attrs["Config"]["Image"] == f"stand-app:{version}"
