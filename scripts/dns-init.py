"""Idempotently configure the local authoritative zone using Technitium's API."""
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


def api(path, **params):
    request = urllib.request.Request(
        "http://technitium:5380/api/" + path,
        data=urllib.parse.urlencode(params).encode(),
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
    if result.get("status") != "ok":
        # Do not log the response: login errors may include sensitive context.
        raise RuntimeError(f"Technitium API {path} failed ({result.get('status')})")
    return result


def main():
    domain = os.environ["LOCAL_DOMAIN"].lower().rstrip(".")
    labels = domain.split(".")
    if len(labels) < 2 or len(domain) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    ):
        raise ValueError("LOCAL_DOMAIN must be a valid multi-label DNS domain")
    address = str(ipaddress.IPv4Address(os.environ["HOST_IP"]))
    password = Path("/run/secrets/dns_admin_password").read_text().strip()
    for attempt in range(60):
        try:
            token = api("user/login", user="admin", **{"pass": password})["token"]
            break
        except (OSError, ValueError, RuntimeError):
            if attempt == 59:
                raise RuntimeError("DNS login failed; check readiness and the stored admin password") from None
            time.sleep(2)
    try:
        zones = api("zones/list", token=token)["response"]["zones"]
        existing = next((z for z in zones if z["name"].lower().rstrip(".") == domain), None)
        if existing is None:
            api("zones/create", token=token, zone=domain, type="Primary")
        elif existing["type"] != "Primary":
            raise RuntimeError("Existing local zone must be Primary")
        # Explicit dns record is needed because the SOA's NS record can prevent
        # wildcard synthesis for the name server itself.
        for name in (domain, f"*.{domain}", f"dns.{domain}"):
            api("zones/records/add", token=token, zone=domain, domain=name,
                type="A", ipAddress=address, ttl=60, overwrite="true")
        token_file = Path("/credentials/api-token")
        valid = False
        if token_file.exists():
            try:
                api("user/session/get", token=token_file.read_text().strip())
                valid = True
            except RuntimeError:
                pass
        if not valid:
            permanent = api("user/createToken", token=token, tokenName="traefik-acme")["token"]
            temporary = token_file.with_suffix(".tmp")
            temporary.write_text(permanent + "\n")
            temporary.chmod(0o600)
            temporary.replace(token_file)
        print(f"Configured {domain}, *.{domain}, dns.{domain} -> {address}")
    finally:
        api("user/logout", token=token)


if __name__ == "__main__":
    main()
