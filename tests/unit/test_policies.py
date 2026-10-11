"""Политики репозитория — без Docker и без состояния Terraform.

Каждая проверка закрывает типичную ошибку: пароль администратора в git, порты открыты всему
интернету, Jenkins с правами root, пайплайн без тестов.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ansible" / "inventory"))

import terraform as tf_inventory  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import plan_guard  # noqa: E402


def _tf(name: str) -> str:
    return (ROOT / "terraform" / name).read_text(encoding="utf-8")


def test_only_nginx_publishes_a_port_and_only_on_configured_address() -> None:
    tf = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "terraform").glob("*.tf"))
    assert tf.count("ports {") == 1
    assert re.search(r"ports \{\s*internal = 8080\s*external = var\.edge_port\s*ip\s*= var\.edge_bind", tf)
    assert re.search(r'variable "edge_bind" \{[^}]*default\s*= "127\.0\.0\.1"', _tf("variables.tf"), re.S)


def test_backend_state_is_not_local_and_has_no_secret() -> None:
    versions = _tf("versions.tf")
    assert 'backend "pg"' in versions
    assert "conn_str" not in versions  # строка подключения — только из PG_CONN_STR


def test_internal_networks() -> None:
    network = _tf("network.tf")
    for name in ("app", "db"):
        block = re.search(rf'resource "docker_network" "{name}" \{{(.*?)\n\}}', network, re.S)
        assert block, f"нет сети {name}"
        assert "internal = true" in block.group(1), f"сеть {name} должна быть внутренней"
    edge = re.search(r'resource "docker_network" "edge" \{(.*?)\n\}', network, re.S)
    assert edge
    assert "internal" not in edge.group(1)


def test_pg_hba_denies_by_default() -> None:
    hba = (ROOT / "terraform" / "templates" / "pg_hba.conf.tftpl").read_text(encoding="utf-8")
    rules = [line.split() for line in hba.splitlines() if line.strip() and not line.startswith("#")]
    assert rules[-1][-1] == "reject"
    network_rules = [r for r in rules if r[0] == "host" and r[-1] != "reject"]
    assert all(r[3] == "${db_subnet}" and r[4] == "scram-sha-256" for r in network_rules)
    assert {r[2] for r in network_rules} == {"replicator", "app"}  # суперпользователю по сети нельзя


def test_compose_has_no_root_and_no_public_ports() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        assert service.get("user") not in ("root", "0"), f"{name} от root"
        assert not service.get("privileged"), f"{name} привилегированный"
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name}: порт {port} открыт на всех интерфейсах"


def test_no_secrets_in_repository() -> None:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.split()
    if not tracked:
        pytest.skip("не git-репозиторий: неизвестно, что попадёт в коммит")
    files = [ROOT / f for f in tracked]
    assert ".env" not in [f.name for f in files]
    pattern = re.compile(r"(password|passwd|secret)\s*[:=]\s*['\"]?(?!\$\{|\{\{|\$\(|\")[A-Za-z0-9_\-]{6,}", re.I)
    leaks = []
    for f in files:
        if f.suffix in {".png", ".lock"} or not f.exists() or f.name == "test_policies.py":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        leaks += [f"{f.relative_to(ROOT)}: {m.group(0)}" for m in pattern.finditer(text)]
    assert leaks == []


def test_jenkinsfile_targets_exist_in_makefile() -> None:
    """Пайплайн — только цели Makefile: всё, что делает Jenkins, разработчик повторит у себя."""
    jenkinsfile = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z-]+):", makefile, re.M))
    used = set(re.findall(r"make (\w[\w-]*)", jenkinsfile))
    assert used <= targets
    assert {"check", "build", "infra", "deploy", "test"} <= used


def test_jenkins_configured_as_code_without_password() -> None:
    casc = (ROOT / "jenkins" / "casc.yaml").read_text(encoding="utf-8")
    assert '"${JENKINS_ADMIN_PASSWORD}"' in casc
    assert "${TF_PG_CONN_STR}" in casc
    dockerfile = (ROOT / "jenkins" / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.rstrip().splitlines()[-1] == "USER jenkins"
    assert "sha256sum -c" in dockerfile  # Terraform проверяется по контрольной сумме


def test_app_image_not_root_with_healthcheck() -> None:
    dockerfile = (ROOT / "app" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile


# ------------------------------------------------------------------ инвентарь

OUTPUTS = {
    "prefix": {"value": "stand"},
    "networks": {"value": {"edge": "stand-edge", "app": "stand-app", "db": "stand-db"}},
    "subnets": {"value": {"edge": "172.30.1.0/24", "app": "172.30.2.0/24", "db": "172.30.3.0/24"}},
    "containers": {"value": {"nginx": "stand-nginx", "primary": "stand-db-primary", "replica": "stand-db-replica"}},
    "edge_url": {"value": "http://127.0.0.1:8080"},
    "app_db_password": {"value": "s3cr3t", "sensitive": True},
    "extra": {"value": 1},
}


def test_inventory_from_terraform_outputs() -> None:
    inv = tf_inventory.inventory(OUTPUTS, python="/usr/bin/python3")
    assert inv["stand"] == {"hosts": ["stand"]}
    host = inv["_meta"]["hostvars"]["stand"]
    assert host["ansible_connection"] == "local"
    assert host["containers"]["primary"] == "stand-db-primary"
    assert host["app_db_password"] == "s3cr3t"
    assert "extra" not in host


def test_inventory_without_apply_explains() -> None:
    with pytest.raises(KeyError, match="terraform apply"):
        tf_inventory.inventory({"prefix": {"value": "stand"}})


def test_migrations_are_ordered_and_named() -> None:
    names = sorted(p.name for p in (ROOT / "ansible/roles/database/files/migrations").glob("*.sql"))
    assert names
    assert all(re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", n) for n in names)
    numbers = [int(n[:3]) for n in names]
    assert numbers == list(range(1, len(names) + 1))


# ------------------------------------------------------------------ проверка плана


def _change(address: str, *actions: str) -> dict[str, object]:
    return {"address": address, "change": {"actions": list(actions)}}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ([_change("docker_container.nginx", "delete", "create")], []),
        ([_change("docker_container.primary", "update")], []),
        ([_change("docker_container.primary", "delete", "create")], ["docker_container.primary: пересоздать"]),
        ([_change("docker_volume.replica", "delete")], ["docker_volume.replica: удалить"]),
        ([_change("docker_network.db", "create", "delete"), _change("docker_container.replica", "create", "delete")],
         ["docker_container.replica: пересоздать"]),
    ],
)
def test_plan_guard(changes: list[dict[str, object]], expected: list[str]) -> None:
    assert plan_guard.dangerous({"resource_changes": changes}) == expected
