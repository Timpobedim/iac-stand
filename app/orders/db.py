"""PostgreSQL через psycopg: соединение на запрос, короткие таймауты."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

CONNECT_TIMEOUT = 3


class PgDb:
    def __init__(self, primary_url: str, replica_url: str) -> None:
        self.urls = {"primary": primary_url, "replica": replica_url}

    def _connect(self, which: str) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.urls[which], connect_timeout=CONNECT_TIMEOUT, row_factory=dict_row, autocommit=True)

    def ping(self, which: str) -> bool:
        try:
            with self._connect(which) as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    def in_recovery(self, which: str) -> bool:
        with self._connect(which) as conn:
            row = conn.execute("SELECT pg_is_in_recovery() AS r").fetchone()
            return bool(row and row["r"])

    def insert_order(self, item: str, qty: int) -> dict[str, Any]:
        with self._connect("primary") as conn:
            row = conn.execute(
                "INSERT INTO orders (item, qty) VALUES (%s, %s) RETURNING id, item, qty, created_at::text", (item, qty)
            ).fetchone()
            if row is None:
                raise RuntimeError("INSERT … RETURNING не вернул строку")
            return dict(row)

    def get_order(self, which: str, order_id: int) -> dict[str, Any] | None:
        with self._connect(which) as conn:
            row = conn.execute(
                "SELECT id, item, qty, created_at::text FROM orders WHERE id = %s", (order_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_orders(self, limit: int) -> list[dict[str, Any]]:
        with self._connect("replica") as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT id, item, qty, created_at::text FROM orders ORDER BY id DESC LIMIT %s", (limit,)
                )
            ]

    def replication(self) -> list[dict[str, Any]]:
        with self._connect("primary") as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT application_name, state, sync_state, "
                    "COALESCE(EXTRACT(EPOCH FROM replay_lag), 0)::float AS replay_lag_seconds "
                    "FROM pg_stat_replication ORDER BY application_name"
                )
            ]
