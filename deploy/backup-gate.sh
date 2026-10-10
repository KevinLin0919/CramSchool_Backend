#!/bin/sh
# Forced command for the backup key, installed on the server.
#
# The backup key has no passphrase so that cron can use it, which means anyone
# who copies the file has it. This gate is what makes that acceptable: the
# server runs it instead of whatever the client asked for, and it lets through
# only the two exports `deploy/backup.sh` sends, character for character.
# Anything else — a shell, a different docker command, the same command with
# something appended — is refused. Read access to the backups is all the key
# is worth.
#
# Exact string comparison on purpose. A pattern would have to be proven not to
# match `...; rm -rf`, and this list changes only when backup.sh does.
case "$SSH_ORIGINAL_COMMAND" in
    "cd CramSchool_Backend && docker compose exec -T db pg_dump -U cram --clean --if-exists cramschool" | \
    "cd CramSchool_Backend && docker compose exec -T api tar cf - -C /data blobs")
        exec sh -c "$SSH_ORIGINAL_COMMAND" ;;
    *)
        echo "backup key: command not allowed" >&2
        exit 1 ;;
esac
