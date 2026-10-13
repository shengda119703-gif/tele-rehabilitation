#!/bin/sh
# Upload only cloud_service, deploy/cloud, and four public visual resources first.
set -eu
if [ "$(id -u)" != 0 ]; then exit 1; fi
test -f /opt/ankang-cloud/current/cloud_service/requirements.txt
cloud_pip_index="${CLOUD_PIP_INDEX_URL:-https://pypi.org/simple}"
case "$cloud_pip_index" in
  https://*) ;;
  *) echo 'Package index must use HTTPS' >&2; exit 1 ;;
esac
if ! id ankang-cloud >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/ankang-cloud --create-home --shell /usr/sbin/nologin ankang-cloud
fi
python3 -m venv /opt/ankang-cloud/venv
/opt/ankang-cloud/venv/bin/python -m pip install --index-url "$cloud_pip_index" -r /opt/ankang-cloud/current/cloud_service/requirements.txt
python3 -m venv /opt/ankang-cloud/certbot
/opt/ankang-cloud/certbot/bin/python -m pip install --index-url "$cloud_pip_index" 'certbot==5.4.0'
install -m 0644 /opt/ankang-cloud/current/deploy/cloud/ankang-cloud.service /etc/systemd/system/ankang-cloud.service
install -m 0755 /opt/ankang-cloud/current/deploy/cloud/backup.sh /usr/local/sbin/ankang-cloud-backup
install -m 0644 /opt/ankang-cloud/current/deploy/cloud/ankang-cloud-backup.service /etc/systemd/system/ankang-cloud-backup.service
install -m 0644 /opt/ankang-cloud/current/deploy/cloud/ankang-cloud-backup.timer /etc/systemd/system/ankang-cloud-backup.timer
install -m 0644 /opt/ankang-cloud/current/deploy/cloud/ankang-cloud-cert-renew.service /etc/systemd/system/ankang-cloud-cert-renew.service
install -m 0644 /opt/ankang-cloud/current/deploy/cloud/ankang-cloud-cert-renew.timer /etc/systemd/system/ankang-cloud-cert-renew.timer
install -d -m 0700 /var/backups/ankang-cloud
install -d -m 0755 /var/www/ankang-acme
systemctl daemon-reload
# HTTPS and credentials must be configured before enabling the API.
