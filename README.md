# Local Docker infrastructure

Traefik, Portainer CE, step-ca, and Technitium DNS with one configurable domain.
Technitium serves the domain and its wildcard; Traefik routes enabled Docker
services as `<compose-service>.<LOCAL_DOMAIN>` and obtains and renews individual
TLS certificates from step-ca over ACME DNS-01.

## Start

Requires Docker Engine, Docker Compose v2.24.4 or newer, Bash, and OpenSSL.

```sh
./scripts/bootstrap.sh
# Edit .env: set LOCAL_DOMAIN, HOST_IP, and ACME_EMAIL.
docker compose config -q
docker compose up -d
docker compose ps -a
```

`HOST_IP` must be the Docker host's static LAN IPv4 address, reachable by clients
and containers. `mylocal.server` is the example domain; prefer a domain you own
or a name under `home.arpa`. Do not use `.local` (reserved for mDNS). The chosen
domain is authoritative locally, so public records below it will be shadowed.
`PROXY_SUBNET` and `DNS_IP` must be an unused subnet and an address inside it.

Set your router's DHCP DNS option, or each client's DNS server, to `HOST_IP`.
Do not advertise a public DNS server as a secondary: clients may use it and fail
to resolve local names. Browser secure DNS and VPN DNS may also bypass local DNS.
Ports TCP/UDP 53 and TCP 80/443 on `HOST_IP` must be available. The DNS console
also binds to `127.0.0.1:5380` for recovery. Bindings are restricted to `HOST_IP`;
allow your LAN through the host firewall and keep these services private.

After startup, export the public root certificate:

```sh
mkdir -p certs
docker compose cp traefik:/ca/root_ca.crt certs/local-root-ca.crt
openssl x509 -in certs/local-root-ca.crt -noout -subject -fingerprint -sha256
```

Install this certificate into each client's trusted root certificate store. For
Debian/Ubuntu clients:

```sh
sudo cp certs/local-root-ca.crt /usr/local/share/ca-certificates/local-root-ca.crt
sudo update-ca-certificates
```

For Windows, import it into **Trusted Root Certification Authorities**; for macOS,
import it into the System keychain and enable trust. Browsers with their own trust
store may need a separate import. Verify the fingerprint through a trusted channel
before installing it on another device. Only distribute the public certificate.

With `LOCAL_DOMAIN=mylocal.server`:

| Service | URL | Login |
| --- | --- | --- |
| Traefik dashboard | `https://traefik.mylocal.server/dashboard/` | `admin`, `secrets/dashboard-password` |
| Portainer | `https://portainer.mylocal.server` | `admin`, `secrets/portainer-password` |
| Technitium | `https://dns.mylocal.server` | `admin`, `secrets/dns-admin-password` |

Portainer's initial admin is created from a password file, avoiding an
unclaimed setup screen. Password files are generated once; rerunning bootstrap
preserves them. Treat `secrets/` as private. Compose file secrets are local files,
not an encrypted secret store. Portainer and Traefik have Docker socket access,
which grants powerful host access, including with a read-only socket mount.

## Add projects

Attach services to the external proxy network and opt in with
`traefik.enable=true`. Specify the application's internal HTTP port. The HTTPS
entry point and step-ca resolver are defaults, so most projects need no router
or TLS labels:

```yaml
services:
  app:
    image: your-app:version
    networks: [proxy]
    labels:
      traefik.enable: "true"
      traefik.http.services.my-app.loadbalancer.server.port: "8080"
networks:
  proxy:
    external: true
    name: local-proxy
```

This becomes `https://app.mylocal.server`. If you changed `PROXY_NETWORK`, use
that name. Use unique service names across projects: two services named `app`
would claim the same hostname. For a custom hostname, add a unique router and
service name, for example:

```yaml
labels:
  traefik.enable: "true"
  traefik.http.routers.billing.rule: Host(`billing.mylocal.server`)
  traefik.http.routers.billing.service: billing
  traefik.http.services.billing.loadbalancer.server.port: "8080"
```

Do not publish application ports unless clients need direct access. Services
with explicit routers should retain the default HTTPS entry point, or specify
`websecure`. Certificates cover concrete hostnames by default; wildcard DNS does not imply
a wildcard TLS certificate. The DNS-01 resolver can also issue wildcard certificates
when explicitly configured with Traefik TLS domain labels.

Try the included service:

```sh
docker compose --env-file .env -p demo -f examples/compose.yaml up -d
# Visit https://whoami.<your-domain>
docker compose --env-file .env -p demo -f examples/compose.yaml down
```

For Portainer stacks, attach applications to the same external network. Explicit
Host rules are useful where stacks do not supply Compose service labels; the
fallback default uses Traefik's normalized container name.

## How bootstrap and certificates work

`ca-init` initializes a persistent CA once and exports only its public root into a
separate volume. Traefik trusts that root via `LEGO_CA_CERTIFICATES`; it never
mounts CA private keys. `dns-init` waits for Technitium, logs in through its API,
creates a Primary zone if missing, and upserts apex, wildcard, and `dns` A records
pointing to `HOST_IP`. Both jobs exit successfully when finished.

step-ca uses Technitium for DNS. Traefik's DNS-01 provider creates temporary TXT
records through Technitium's API, and step-ca validates them directly on the
Docker network. The DNS bootstrap job creates and persists a non-expiring API
token in `dns-acme`, mounted read-only into Traefik. This token has administrator
permissions: protect this volume like a password. It is reused on subsequent
runs and replaced if revoked. You can revoke it from Technitium's Sessions UI.
For deployments requiring narrower permissions, provision a dedicated DNS user
and replace the token with one limited to this zone.

Traefik checks propagation using the internal DNS address and skips public
authoritative-server checks; all certificate validation still runs. Public DNS,
port forwarding, and container-to-host reflection are unnecessary for issuance.
step-ca's 24-hour certificate lifetime is reflected in Traefik's renewal setting.
Traefik redirects HTTP to HTTPS. There is no TLS verification bypass.

The CA endpoint is `https://step-ca:9000/acme/acme/directory` inside the proxy
network. It is intentionally not published to the LAN. The ACME provisioner
allows certificates for names whose DNS challenges it can validate. Restrict
network membership to trusted containers; this setup does not add issuance
policies or external account binding.

## Maintenance and diagnosis

```sh
docker compose logs dns-init ca-init step-ca traefik
dig @<HOST_IP> random.<LOCAL_DOMAIN> A
curl --cacert certs/local-root-ca.crt https://portainer.<LOCAL_DOMAIN>/
```

If local client DNS is not configured yet:

```sh
curl --resolve portainer.mylocal.server:443:<HOST_IP> \
  --cacert certs/local-root-ca.crt https://portainer.mylocal.server/
```

An initial Traefik fallback certificate can appear while issuance completes.
Check Traefik logs for successful ACME issuance; on failure, check DNS resolution
and API token access to Technitium. A CA failure prevents initial Traefik startup
through its health dependency. Recovery DNS UI: `http://127.0.0.1:5380` on the host.

Technitium's environment settings and Portainer's admin password file initialize new data
only. Change existing passwords in their UIs, then update the matching local secret
where needed (the DNS bootstrap job requires the current DNS admin password).
To reconcile zone records after changing `HOST_IP` or the domain:

```sh
docker compose up -d technitium
docker compose run --rm dns-init
docker compose up -d
```

Old domain zones are retained; remove them deliberately through Technitium if no
longer needed. The CA's initial `ca.<domain>` SAN is also retained when the domain
changes; Traefik uses the stable `step-ca` name. Changes to network addressing
require recreating the Docker network with `docker compose down` first.

Back up all named volumes and `secrets/`, especially `ca-data` and `acme-data`,
while services are stopped, and store backups securely. Losing the CA means
reinstalling a new root on every client. `docker compose down` preserves volumes;
`docker compose down -v` destroys the CA and other persistent data.

Image channels are configurable in `.env`; pin digests for reproducible upgrades.
To update intentionally: `docker compose pull && docker compose up -d`.

## References

- [Technitium environment settings](https://github.com/TechnitiumSoftware/DnsServer/blob/master/DockerEnvironmentVariables.md)
- [Technitium API](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md)
- [Traefik Docker provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/docker/)
- [Traefik ACME settings](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/)
- [Technitium ACME DNS provider](https://go-acme.github.io/lego/dns/technitium/)
- [Smallstep ACME clients and private root trust](https://smallstep.com/docs/tutorials/acme-protocol-acme-clients/)
