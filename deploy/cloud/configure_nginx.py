"""Render scoped host config; never change SSH or expose the DB/API port."""
import argparse
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
import ipaddress


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args()
    parsed = urlsplit(args.origin)
    host = parsed.hostname
    if parsed.scheme != "https" or parsed.path or parsed.port or not host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host):
        parser.error("Use an exact HTTPS IPv4/domain origin")
    acme = "location ^~ /.well-known/acme-challenge/ { root /var/www/ankang-acme; }"
    clear = f"server {{\n listen 80;\n server_name {host};\n {acme}\n location / {{ return 308 https://{host}$request_uri; }}\n}}\n"
    if args.tls:
        tls = f"""server {{
 listen 443 ssl http2;
 server_name {host};
 ssl_certificate /etc/letsencrypt/live/{host}/fullchain.pem;
 ssl_certificate_key /etc/letsencrypt/live/{host}/privkey.pem;
 ssl_protocols TLSv1.2 TLSv1.3;
 client_max_body_size 3m;
 client_body_timeout 10s;
 access_log off;
 add_header Strict-Transport-Security "max-age=604800" always;
 location / {{
   proxy_pass http://127.0.0.1:8780;
   proxy_set_header Host $host;
   proxy_set_header X-Forwarded-Proto https;
   proxy_set_header X-Forwarded-For $remote_addr;
   proxy_connect_timeout 3s;
   proxy_read_timeout 20s;
 }}
}}
"""
        clear += tls
    Path("/etc/nginx/sites-available/ankang-cloud").write_text(clear, encoding="utf-8")
    enabled = Path("/etc/nginx/sites-enabled/ankang-cloud")
    if not enabled.exists():
        enabled.symlink_to("/etc/nginx/sites-available/ankang-cloud")
    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)


if __name__ == "__main__":
    main()
