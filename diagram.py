"""Render the architecture defined in compose.yaml and examples/compose.yaml.

Requires the Python ``diagrams`` package and the Graphviz ``dot`` executable.
Run ``python diagram.py`` to write local-env.png in the current directory.
Solid arrows show runtime interactions; dashed arrows show initialization and
persistent storage access. The whoami service is an optional example stack.
"""

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.container import Docker
from diagrams.onprem.network import Traefik


def volume(name):
    """Named Docker volume, drawn without a service-specific icon."""
    return Node(name, shape="cylinder")


with Diagram(
    "Local Docker infrastructure",
    filename="local-env",
    show=False,
    direction="LR",
    graph_attr={"pad": "0.5", "nodesep": "0.6", "ranksep": "1.2"},
):
    clients = Users("LAN clients\ntrust exported root CA")

    with Cluster("Docker host — HOST_IP"):
        docker = Docker("Docker Engine\n/var/run/docker.sock")

        with Cluster("proxy network — PROXY_NETWORK (default: local-proxy)"):
            dns = Server("technitium\nDNS :53 TCP/UDP\nconsole :5380")
            proxy = Traefik("traefik\n:80 redirects to :443\ntraefik.LOCAL_DOMAIN/dashboard/")
            ca = Server("step-ca\nprivate ACME CA :9000\ninternal only")
            portainer = Server("portainer\nportainer.LOCAL_DOMAIN\nHTTP backend :9000")

            with Cluster("One-shot initialization jobs"):
                dns_init = Server("dns-init\nscripts/dns-init.py")
                ca_init = Server("ca-init\nscripts/ca-init.sh")

            with Cluster("Optional example — examples/compose.yaml"):
                whoami = Server("whoami\nwhoami.LOCAL_DOMAIN\nHTTP backend :80")

        with Cluster("Persistent named volumes"):
            dns_data = volume("dns-data\nDNS configuration")
            dns_acme = volume("dns-acme\nTechnitium API token")
            ca_data = volume("ca-data\nCA configuration and private keys")
            ca_public = volume("ca-public\npublic root certificate")
            acme_data = volume("acme-data\nACME account and certificates")
            portainer_data = volume("portainer-data\nPortainer state")

    clients >> Edge(label="DNS :53\napex / wildcard → HOST_IP") >> dns
    clients >> Edge(label="HTTP :80 / HTTPS :443") >> proxy
    proxy >> Edge(label="dns.LOCAL_DOMAIN → :5380") >> dns
    proxy >> Edge(label="HTTP :9000") >> portainer
    proxy >> Edge(label="HTTP :80") >> whoami
    proxy >> Edge(label="Docker provider / labels\nread-only socket mount") >> docker
    portainer >> Edge(label="manage containers\nDocker socket") >> docker

    proxy >> Edge(label="ACME issuance / renewal\nHTTPS :9000") >> ca
    proxy >> Edge(label="DNS-01 TXT records\nTechnitium API :5380") >> dns
    ca >> Edge(label="DNS-01 validation\ninternal DNS :53") >> dns

    dns_init >> Edge(label="wait for DNS; configure zone,\nA records and API token", style="dashed") >> dns
    ca_init >> Edge(label="initialize", style="dashed") >> ca_data
    ca_init >> Edge(label="export root", style="dashed") >> ca_public
    dns_init >> Edge(label="write token", style="dashed") >> dns_acme
    dns_init >> Edge(label="completed before startup", style="dashed") >> ca
    ca_init >> Edge(label="completed before startup", style="dashed") >> ca
    ca >> Edge(label="healthy before startup", style="dashed") >> proxy

    dns >> Edge(style="dashed", label="read/write") >> dns_data
    ca >> Edge(style="dashed", label="read/write") >> ca_data
    proxy >> Edge(style="dashed", label="read root (RO)") >> ca_public
    proxy >> Edge(style="dashed", label="read token (RO)") >> dns_acme
    proxy >> Edge(style="dashed", label="read/write") >> acme_data
    portainer >> Edge(style="dashed", label="read/write") >> portainer_data
