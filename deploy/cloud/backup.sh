#!/bin/sh
set -eu
umask 077
backup_target="/var/backups/ankang-cloud/$(date -u +%Y%m%dT%H%M%SZ).dump.enc"
backup_temp="$(mktemp /var/backups/ankang-cloud/staging.XXXXXX)"
trap 'rm -f -- "$backup_temp"' EXIT
runuser -u postgres -- pg_dump --format=custom ankang_cloud > "$backup_temp"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -in "$backup_temp" -out "$backup_target" -pass file:/etc/ankang-cloud/backup.key
test -s "$backup_target"
# Independent/off-host copying is an operations step, not implied by this dump.
