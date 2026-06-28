#!/bin/sh
set -eu

mkdir -p /certs

CERT_CN="${CERT_CN:-shelfquest.local}"
CERT_ALT_NAMES="${CERT_ALT_NAMES:-DNS:shelfquest.local,DNS:localhost,IP:127.0.0.1}"

if [ ! -s /certs/shelfquest.crt ] || [ ! -s /certs/shelfquest.key ]; then
  echo "Generating ShelfQuest self-signed HTTPS certificate..."
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /certs/shelfquest.key \
    -out /certs/shelfquest.crt \
    -subj "/CN=${CERT_CN}/O=ShelfQuest Home Library" \
    -addext "subjectAltName=${CERT_ALT_NAMES}"
fi

exec "$@"
