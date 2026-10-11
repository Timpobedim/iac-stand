#!/bin/sh
# Реплика: при первом запуске копирует основную базу (pg_basebackup -R пишет standby.signal
# и строку подключения), дальше просто запускает PostgreSQL в режиме горячего резерва.
set -eu
PGDATA=/var/lib/postgresql/data
export PGPASSWORD="$REPLICATOR_PASSWORD"

until pg_isready -h "$PRIMARY_HOST" -U replicator -d orders -q; do
    echo "жду основную базу $PRIMARY_HOST"
    sleep 1
done

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "первый запуск: копирую основную базу"
    mkdir -p "$PGDATA"
    chown postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    su-exec postgres pg_basebackup -h "$PRIMARY_HOST" -U replicator -D "$PGDATA" \
        -R -X stream -S replica_1 --checkpoint=fast --no-password
fi
unset PGPASSWORD

exec su-exec postgres postgres -c hot_standby=on -c hba_file=/etc/postgresql/pg_hba.conf
