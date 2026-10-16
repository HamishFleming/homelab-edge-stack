#!/usr/bin/env bash
# Configure this Linux client's DNS and system CA trust for the local stack.
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 3 ]]; then
  echo "Usage: sudo $0 DOMAIN HOST_IPV4 ROOT_CA_CERTIFICATE" >&2
  exit 1
fi
domain=$1
host_ip=$2
certificate=$3
python3 - "$domain" "$host_ip" <<'PY'
import ipaddress, re, sys
assert re.fullmatch(r'[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+', sys.argv[1]), 'Invalid domain'
ipaddress.IPv4Address(sys.argv[2])
PY
openssl x509 -in "$certificate" -noout >/dev/null
if command -v update-ca-trust >/dev/null; then
  install -Dm644 "$certificate" /etc/ca-certificates/trust-source/anchors/local-env-root-ca.crt
  update-ca-trust
elif command -v update-ca-certificates >/dev/null; then
  install -Dm644 "$certificate" /usr/local/share/ca-certificates/local-env-root-ca.crt
  update-ca-certificates
else
  echo 'No supported system trust update command found.' >&2
  exit 1
fi
install -d /etc/systemd/resolved.conf.d
config=/etc/systemd/resolved.conf.d/local-env.conf
if [[ -f $config ]]; then
  cp -a "$config" "$config.bak.$(date +%s)"
fi
printf '[Resolve]\nDNS=%s\nDomains=~%s\n' "$host_ip" "$domain" > "$config"
systemctl restart systemd-resolved
resolvectl query "traefik.$domain"
