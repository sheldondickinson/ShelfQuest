# ShelfQuest v0.1.8 - HTTPS Proxy Update

This build keeps the app itself simple and adds a small Nginx reverse proxy in front of it.

## Ports

- HTTP: `http://<qnap-ip>:8123`
- HTTPS: `https://<qnap-ip>:8443`

## Certificate

A self-signed certificate is generated automatically on first start and stored in:

`./data/certs`

Because it is self-signed, browsers will show a privacy warning. This is expected.

## Upgrade

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v018-$(date +%Y%m%d-%H%M).db
docker compose down
docker compose up -d --build
```

After the first build, open:

`https://<qnap-ip>:8443`

Accept the browser warning if prompted.

## Optional: include your QNAP IP in the generated self-signed certificate

Before the first HTTPS start, edit `docker-compose.yml` and change:

```yaml
- CERT_ALT_NAMES=DNS:shelfquest.local,DNS:localhost,IP:127.0.0.1
```

For example:

```yaml
- CERT_ALT_NAMES=DNS:shelfquest.local,DNS:localhost,IP:127.0.0.1,IP:192.168.1.50
```

If a certificate was already generated, delete the old cert files and restart:

```bash
rm -f data/certs/shelfquest.crt data/certs/shelfquest.key
docker compose up -d --build
```

## Notes

- Existing `docker exec -it shelfquest ...` importer commands still work.
- The admin password remains `Letmein!2`.
- Camera barcode scanning still depends on browser support and whether the browser accepts the page as a secure context.
