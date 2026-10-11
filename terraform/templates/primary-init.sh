#!/bin/sh
# Выполняется один раз, при создании базы: роль для репликации и слот для реплики.
# Слот не даёт основной базе удалить WAL, который реплика ещё не забрала.
set -eu
psql -v ON_ERROR_STOP=1 -U postgres -d orders <<SQL
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${REPLICATOR_PASSWORD}';
SELECT pg_create_physical_replication_slot('replica_1');
SQL
