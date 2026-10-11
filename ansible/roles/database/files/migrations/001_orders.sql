-- Таблица заказов. Ограничения те же, что в модели сервиса: база не примет то,
-- что сервис отверг бы, даже если запишут в обход сервиса.
CREATE TABLE orders (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item        text        NOT NULL CHECK (length(item) BETWEEN 1 AND 100),
    qty         integer     NOT NULL CHECK (qty BETWEEN 1 AND 1000),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Сервису — только чтение и вставка: ни UPDATE, ни DELETE, ни DDL.
GRANT SELECT, INSERT ON orders TO app;
