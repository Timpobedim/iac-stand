"""Сервис заказов: пишет в основную базу, читает с реплики.

Чтение с реплики — повод показать, что репликация асинхронная: только что созданного
заказа на реплике может ещё не быть. Тогда сервис читает с основной базы и говорит об этом
заголовком X-Read-From, а не притворяется, что задержки нет.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field


class Db(Protocol):
    def ping(self, which: str) -> bool: ...
    def in_recovery(self, which: str) -> bool: ...
    def insert_order(self, item: str, qty: int) -> dict[str, Any]: ...
    def get_order(self, which: str, order_id: int) -> dict[str, Any] | None: ...
    def list_orders(self, limit: int) -> list[dict[str, Any]]: ...
    def replication(self) -> list[dict[str, Any]]: ...


def get_db(request: Request) -> Db:
    db: Db = request.app.state.db
    return db


Database = Annotated[Db, Depends(get_db)]


class OrderIn(BaseModel):
    item: Annotated[str, Field(min_length=1, max_length=100)]
    qty: Annotated[int, Field(ge=1, le=1000)]


def create_app(db: Db, version: str) -> FastAPI:
    app = FastAPI(title="orders", version=version)
    app.state.db = db

    @app.get("/health")
    def health(response: Response, db: Database) -> dict[str, str]:
        """Здоров, только если доступны обе базы и реплика действительно реплика."""
        state = {"version": version, "primary": "ok", "replica": "ok"}
        if not db.ping("primary"):
            state["primary"] = "unavailable"
        if not db.ping("replica"):
            state["replica"] = "unavailable"
        elif not db.in_recovery("replica"):
            state["replica"] = "not a standby"
        if state["primary"] != "ok" or state["replica"] != "ok":
            response.status_code = 503
        return state

    @app.get("/version")
    def get_version() -> dict[str, str]:
        return {"version": version}

    @app.post("/orders", status_code=201)
    def create_order(order: OrderIn, db: Database) -> dict[str, Any]:
        return db.insert_order(order.item, order.qty)

    @app.get("/orders/{order_id}")
    def get_order(order_id: int, response: Response, db: Database) -> dict[str, Any]:
        found = db.get_order("replica", order_id)
        response.headers["X-Read-From"] = "replica"
        if found is None:
            # Реплика могла ещё не догнать основную базу — это не «заказа нет».
            found = db.get_order("primary", order_id)
            response.headers["X-Read-From"] = "primary"
        if found is None:
            raise HTTPException(status_code=404, detail=f"заказа {order_id} нет")
        return found

    @app.get("/orders")
    def list_orders(db: Database, limit: int = 20) -> list[dict[str, Any]]:
        return db.list_orders(max(1, min(limit, 100)))

    @app.get("/replication")
    def replication(db: Database) -> list[dict[str, Any]]:
        """Состояние потоковой репликации с точки зрения основной базы (pg_stat_replication)."""
        return db.replication()

    return app


def build() -> FastAPI:
    """Точка входа для uvicorn: настоящая база из переменных окружения."""
    from orders.db import PgDb

    return create_app(PgDb(os.environ["PRIMARY_URL"], os.environ["REPLICA_URL"]), os.environ.get("APP_VERSION", "dev"))
