#!/bin/sh
# Sauvegarde : base (pg_dump compressé) + images. À lancer depuis deploy/ (cron quotidien conseillé).
#   0 4 * * * cd /opt/syncron/deploy && ./backup.sh >> backup.log 2>&1
set -eu
STAMP=$(date +%Y%m%d-%H%M%S)
DEST=${BACKUP_DIR:-./backups}
mkdir -p "$DEST"
docker compose exec -T db pg_dump -U syncron -d syncron --format=custom > "$DEST/syncron-$STAMP.dump"
docker compose run --rm --no-deps -v "$(pwd)/$DEST:/backup" --entrypoint tar api \
    czf "/backup/media-$STAMP.tar.gz" -C /data media
find "$DEST" -type f -mtime +${KEEP_DAYS:-14} -delete
echo "Sauvegarde terminée : $DEST/syncron-$STAMP.dump"
