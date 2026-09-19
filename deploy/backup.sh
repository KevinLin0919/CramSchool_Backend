#!/usr/bin/env bash
# Pull a full backup of the grading server to this machine.
#
# Pull, not push. A cron on the server writing to the server's own disk
# defends against `docker compose down -v` and a bad migration, and against
# nothing else — not the laptop being dropped, stolen from the cram school, or
# simply having its disk fail. Run from somewhere else and all of those are
# covered, with no extra moving part on the machine teachers depend on.
#
# Two halves, and a backup is only a backup with both. The database holds rows
# that reference images by id; without the blobs, every one of those images
# answers 410 and the restored record is a score with no evidence behind it.
#
# The blob store is content-addressed and append-only — a file's name is the
# SHA-256 of its contents, so it is never rewritten. `rsync` therefore copies
# only what is new, where a daily `tar` would recompress the same bytes
# forever. `derivatives/` is deliberately skipped: it is a cache, and
# restoring it costs nothing but CPU.
#
#   usage: deploy/backup.sh [destination]
#   cron:  17 3 * * *  /path/to/deploy/backup.sh >> ~/backups/backup.log 2>&1
set -euo pipefail

HOST="${BACKUP_HOST:-comma@100.107.235.123}"
REMOTE_DIR="${BACKUP_REMOTE_DIR:-CramSchool_Backend}"
DEST="${1:-${BACKUP_DEST:-$HOME/backups/cramschool}}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST/db" "$DEST/blobs"

echo "==> 備份資料庫"
DUMP="$DEST/db/cramschool-$STAMP.sql.gz"
# --clean --if-exists so the dump can be replayed into a database that already
# has a schema, which is what a restore test actually looks like.
ssh -o BatchMode=yes "$HOST" \
    "cd $REMOTE_DIR && docker compose exec -T db pg_dump -U cram --clean --if-exists cramschool" \
    | gzip > "$DUMP.partial"
# Rename only after the pipe closed cleanly. A truncated dump that looks like
# a finished one is worse than no dump: it is discovered at restore time.
mv "$DUMP.partial" "$DUMP"
echo "    $(du -h "$DUMP" | cut -f1)  $DUMP"

echo "==> 備份影像"
# The blobs live inside a Docker volume, so they come out through the
# container rather than off the host filesystem.
#
# Into a staging directory first, then rsync across. Extracting straight onto
# the existing copy would leave it half-old and half-new if the transfer died
# partway, and the point of this file is to be trustworthy on the one day it
# is needed.
STAGING="$DEST/.blobs.incoming"
rm -rf "$STAGING"
mkdir -p "$STAGING"
ssh -o BatchMode=yes "$HOST" \
    "cd $REMOTE_DIR && docker compose exec -T api tar cf - -C /data blobs" \
    | tar xf - -C "$STAGING"
# `--delete` so a blob removed upstream is removed here too; the store is
# append-only in practice, so this should never actually delete anything, and
# if it does that is worth seeing in the log.
rsync -a --delete -v "$STAGING/blobs/" "$DEST/blobs/" | tail -3
rm -rf "$STAGING"
echo "    $(du -sh "$DEST/blobs" | cut -f1)  $DEST/blobs"

echo "==> 清理超過 $KEEP_DAYS 天的資料庫備份"
find "$DEST/db" -name 'cramschool-*.sql.gz' -mtime "+$KEEP_DAYS" -print -delete

echo "==> 完成：$(ls -1 "$DEST/db" | wc -l) 份資料庫備份，影像 $(find "$DEST/blobs" -type f | wc -l) 個檔案"
