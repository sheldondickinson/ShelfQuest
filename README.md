# ShelfQuest v0.1.3

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

## QNAP / ARM build note

If your QNAP is ARM based, avoid `uvicorn[standard]` because it pulls in optional compiled packages such as `httptools` and `uvloop`. This package uses plain `uvicorn` instead so the image can build without a C compiler.


## v0.1.3 notes

Adds explicit CSV/import support for a `Barcode` column. Existing databases are still compatible.

Expected CSV columns for the importer:

```text
ISBN,Barcode,Qty,Title,Author,Illustrator,Synopsis,Category,CoverURL
```

If `Barcode` is blank, the importer falls back to using the ISBN as the temporary scan code. If `Barcode` is populated, the app stores it as the scannable copy code while still keeping ISBN on the title record for lookup/fallback scanning.
