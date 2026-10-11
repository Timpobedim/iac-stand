-- Список заказов читается от новых к старым.
CREATE INDEX orders_created_at_idx ON orders (created_at DESC);
