# ShelfQuest v0.1

A small self-hosted home library web app for kids, barcode scanners and ISBN-first borrowing.

## Default local URL

http://<your-qnap-ip>:8123

## Quick start with Docker Compose

```bash
mkdir -p shelfquest/data
cd shelfquest
# copy docker-compose.yml, Dockerfile and app/ into this folder
docker compose up -d --build
```

## Notes

- This v0.1 is intended for a trusted home LAN only. It has no login system yet.
- ISBN scanning is supported as the temporary book barcode.
- When you later print your own labels, add a new copy barcode such as BK000001.
- USB barcode scanners normally act like a keyboard, so scan into any focused input field.
