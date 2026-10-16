#!/bin/sh
set -eu
export LOCAL_DOMAIN
chown step:step /home/step /public
if [ ! -f /home/step/config/ca.json ]; then
  su step -s /bin/sh -c 'step ca init --deployment-type standalone \
    --name "Local Development CA" --dns "step-ca,ca.${LOCAL_DOMAIN}" \
    --address :9000 --provisioner admin --acme \
    --password-file /run/secrets/ca_password'
fi
# Export only the public trust anchor. Traefik never receives the CA private keys.
cp /home/step/certs/root_ca.crt /public/root_ca.crt
chmod 644 /public/root_ca.crt
