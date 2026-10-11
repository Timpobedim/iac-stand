#!/usr/bin/env python3
"""Не применять план, который удаляет или пересоздаёт данные.

    terraform show -json tfplan | python3 scripts/plan_guard.py

Защищены базы и их тома: пересоздание контейнера базы — это простой, а тома — потеря данных.
Такой план требует человека: ALLOW_DATA_REPLACE=yes в окружении.

Проверка появилась после настоящего случая: провайдер Docker видел разницу в шлюзе сети
при каждом plan и предлагал пересоздать сети, а с ними — основную базу и реплику.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

PROTECTED = {
    "docker_container.primary",
    "docker_container.replica",
    "docker_volume.primary",
    "docker_volume.replica",
}


def dangerous(plan: dict[str, Any]) -> list[str]:
    """Защищённые ресурсы, которые план удаляет или пересоздаёт."""
    found = []
    for change in plan.get("resource_changes", []):
        actions = change.get("change", {}).get("actions", [])
        if change.get("address") in PROTECTED and "delete" in actions:
            what = "пересоздать" if "create" in actions else "удалить"
            found.append(f"{change['address']}: {what}")
    return found


def main() -> int:
    problems = dangerous(json.load(sys.stdin))
    if not problems:
        print("план не трогает данные")
        return 0
    print("план затрагивает данные:\n  " + "\n  ".join(problems))
    if os.environ.get("ALLOW_DATA_REPLACE") == "yes":
        print("разрешено явно: ALLOW_DATA_REPLACE=yes")
        return 0
    print("не применяю. Если это намеренно — ALLOW_DATA_REPLACE=yes")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
