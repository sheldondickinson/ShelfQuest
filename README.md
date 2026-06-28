# ShelfQuest v0.1.7

Home library app for kids and tired adults.

## New in v0.1.7

- Admin book list pagination.
- More mobile-responsive admin and kid screens.
- Camera scan buttons beside barcode/ISBN scan fields.
- Child photos, including upload/edit through Admin.
- Visual child picker cards in Kid Kiosk.
- Admin password gate.

## Admin password

Default password is configured in `docker-compose.yml`:

```yaml
ADMIN_PASSWORD=Letmein!2
```

The browser stores a temporary admin token in local storage after login. If the container restarts, login again.

## Camera scanning note

The camera scan button uses the browser's built-in BarcodeDetector API where available. Many mobile browsers require HTTPS before allowing camera access on a LAN-hosted web app. USB barcode scanners and manual typing continue to work.

## Upgrade

1. Back up your database:

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v017-$(date +%Y%m%d-%H%M).db
```

2. Copy the contents of this folder over `/share/Container/shelfquest`.

3. Do not delete the `data` folder.

4. Rebuild:

```bash
docker compose down
docker compose up -d --build
```

5. Hard refresh your browser:

```text
Ctrl + F5
```

## Data folders

The app stores persistent data in `/data` inside the container, mounted from `./data` on the QNAP.

- SQLite database: `/data/library.db`
- Book covers: `/data/covers`
- Child photos: `/data/children`

## API protection

Kid functions remain open on the local LAN:

- Child list
- Book list/search
- Checkout
- Return
- Active loans

Admin changes require the admin token:

- Add/edit child
- Upload child photo
- Add/edit/delete book
- Upload/cache covers
- Mark damaged/repaired
