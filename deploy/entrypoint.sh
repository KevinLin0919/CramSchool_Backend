#!/bin/sh
set -eu

# The data volume's ownership comes from the host, so it cannot be fixed at
# build time. Do it here, then drop privileges for the actual process.
mkdir -p "${DATA_DIR:-/data}/blobs" "${DATA_DIR:-/data}/derivatives"
chown -R cram:cram "${DATA_DIR:-/data}" 2>/dev/null || true

# Wait for the database to accept connections.
#
# `depends_on: service_healthy` covers `docker compose up` and nothing else:
# on a host reboot the daemon restarts containers by policy and does not
# re-evaluate the condition, so the API races Postgres, the migration below
# fails under `set -e`, and the container dies. The restart policy brings it
# back and it self-heals in under a minute — but that minute is exactly when
# a teacher decides the server is broken, and after this is reachable from
# outside the building they cannot walk over to see that it is not.
echo "==> 等待資料庫"
i=0
until python3 -c "
import os, sys, urllib.parse as u
import psycopg
d = u.urlparse(os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://'))
psycopg.connect(host=d.hostname, port=d.port or 5432, user=d.username,
                password=d.password, dbname=d.path.lstrip('/'),
                connect_timeout=3).close()
" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
        echo "資料庫 60 次嘗試後仍無回應，放棄" >&2
        exit 1
    fi
    sleep 2
done
echo "==> 資料庫已就緒（等了 $((i * 2)) 秒）"

# Schema changes are applied on start rather than by hand. Migrations are
# forward-only and idempotent, so a restart is safe; a container that cannot
# migrate must not start and serve against a schema it does not understand.
echo "==> 套用資料庫 migration"
su cram -s /bin/sh -c "alembic upgrade head"

echo "==> 啟動 API"
exec su cram -s /bin/sh -c "exec $*"
