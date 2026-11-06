
#!/usr/bin/env bash
set -uo pipefail

OUT="network-report-$(hostname)-$(date +%Y%m%d-%H%M%S).txt"

section() {
  printf '\n\n========== %s ==========\n' "$1"
}

run() {
  printf '\n$ %s\n' "$*"
  "$@" 2>&1 || true
}

{
  section "HOST"
  run hostnamectl
  run uname -a

  section "NETWORK INTERFACES"
  run ip -br addr
  run ip -d link show

  section "ROUTING"
  run ip route
  run ip -6 route
  run ip rule

  section "DNS"
  run cat /etc/resolv.conf
  command -v resolvectl >/dev/null && run resolvectl status

  section "LISTENING PORTS"
  run ss -tuln

  section "NETWORK BRIDGES"
  if command -v bridge >/dev/null; then
    run bridge link show
    run bridge vlan show
  fi

  section "DOCKER CONTAINERS"
  if command -v docker >/dev/null; then
    run docker ps -a --format \
      'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'

    section "DOCKER NETWORKS"
    run docker network ls

    section "DOCKER NETWORK DETAILS"
    docker network ls -q | while read -r id; do
      docker network inspect "$id" \
        --format 'Name: {{.Name}}
Driver: {{.Driver}}
Subnet: {{range .IPAM.Config}}{{.Subnet}} {{end}}
Gateway: {{range .IPAM.Config}}{{.Gateway}} {{end}}
Containers: {{range .Containers}}{{.Name}}={{.IPv4Address}} {{end}}'
    done

    section "CONTAINER NETWORK MEMBERSHIP"
    docker ps -aq | while read -r id; do
      docker inspect "$id" \
        --format '{{.Name}} | {{.Config.Image}} | {{range $name, $net := .NetworkSettings.Networks}}{{$name}}={{$net.IPAddress}} {{end}}'
    done
  fi

  section "VIRTUAL MACHINES"
  if command -v virsh >/dev/null; then
    run virsh list --all
    run virsh net-list --all
  fi

  section "WIREGUARD"
  if command -v wg >/dev/null; then
    run wg show interfaces
  fi

} > "$OUT"

echo "Report saved to: $OUT"

