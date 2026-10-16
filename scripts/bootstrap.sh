#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v openssl >/dev/null || { echo 'Install openssl first.' >&2; exit 1; }
umask 077
mkdir -p secrets
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
for name in ca-password dns-admin-password dashboard-password portainer-password; do
  if [[ ! -s secrets/$name ]]; then
    openssl rand -hex 24 > "secrets/$name"
  fi
done
if [[ ! -s secrets/dashboard-users ]]; then
  printf 'admin:%s\n' "$(openssl passwd -apr1 -stdin < secrets/dashboard-password)" > secrets/dashboard-users
fi
# Docker Compose file secrets retain source permissions. The non-root CA must
# read its password; the enclosing 0700 directory protects these on the host.
chmod 700 secrets
chmod 644 secrets/ca-password
printf '%s\n' 'Secrets ready. Set LOCAL_DOMAIN, HOST_IP and ACME_EMAIL in .env, then run docker compose up -d.'
