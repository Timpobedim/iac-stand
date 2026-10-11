#!/usr/bin/env python3
"""Динамический инвентарь Ansible из `terraform output -json`.

Ansible узнаёт о стенде то, что создал Terraform: имена сетей и контейнеров, адрес входа
и пароль роли сервиса. Ничего не копируется руками и не расходится после terraform apply.
Пароль приходит из состояния Terraform (оно в PostgreSQL) и в инвентарь на диске не пишется.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

TERRAFORM_DIR = Path(__file__).resolve().parents[2] / "terraform"
HOST = "stand"


def terraform_outputs(directory: Path = TERRAFORM_DIR) -> dict[str, Any]:
    raw = subprocess.run(  # noqa: S603
        ["terraform", f"-chdir={directory}", "output", "-json"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(raw)  # type: ignore[no-any-return]


def inventory(outputs: dict[str, Any], python: str = sys.executable) -> dict[str, Any]:
    """Превратить выходы Terraform в инвентарь: одна группа stand с одним локальным хостом."""
    required = {"prefix", "networks", "containers", "subnets", "edge_url", "app_db_password"}
    missing = sorted(required - outputs.keys())
    if missing:
        raise KeyError(f"в состоянии Terraform нет выходов: {', '.join(missing)} — сначала terraform apply")
    hostvars = {name: outputs[name]["value"] for name in sorted(required)}
    return {
        "stand": {"hosts": [HOST]},
        "_meta": {
            "hostvars": {HOST: {"ansible_connection": "local", "ansible_python_interpreter": python, **hostvars}}
        },
    }


def main(argv: list[str]) -> int:
    if "--host" in argv:
        print(json.dumps({}))
        return 0
    directory = Path(os.environ.get("STAND_TERRAFORM_DIR", TERRAFORM_DIR))
    print(json.dumps(inventory(terraform_outputs(directory))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
