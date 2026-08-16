#!/bin/sh
set -eu

# The data volume's ownership comes from the host, so it cannot be fixed at
# build time. Do it here, then drop privileges for the actual process.
mkdir -p "${DATA_DIR:-/data}/blobs" "${DATA_DIR:-/data}/derivatives"
chown -R cram:cram "${DATA_DIR:-/data}" 2>/dev/null || true

# Schema changes are applied on start rather than by hand. Migrations are
# forward-only and idempotent, so a restart is safe; a container that cannot
# migrate must not start and serve against a schema it does not understand.
echo "==> 套用資料庫 migration"
su cram -s /bin/sh -c "alembic upgrade head"

echo "==> 啟動 API"
exec su cram -s /bin/sh -c "exec $*"
