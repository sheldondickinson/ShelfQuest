# ShelfQuest

ShelfQuest is a small self-hosted home library web app designed for families who want to keep children’s books organised without running a full institutional library system.

It lets kids choose their library card, search for books, scan barcodes, borrow books and return them. Parents get an admin interface for importing books, editing metadata, uploading covers, managing children, marking books as damaged, and bulk-returning borrowed books.

The project is intentionally lightweight:

- **Backend:** Python / FastAPI
- **Database:** SQLite
- **Frontend:** HTML, Bootstrap-style CSS and JavaScript
- **Hosting:** Docker / Docker Compose
- **Target environment:** QNAP NAS, Raspberry Pi kiosk, phones, tablets or any browser on the home network

---

## What ShelfQuest does

ShelfQuest is built around a simple home-library workflow:

1. A child chooses their library card.
2. The child scans or enters a book barcode.
3. ShelfQuest records the loan.
4. Returned books are scanned or bulk-returned by an adult.
5. Parents can maintain the catalogue from the admin interface.

It supports both the early **ISBN-only phase** and a later **custom barcode label phase**.

During the ISBN-only phase, ShelfQuest can use the book’s existing ISBN barcode as the temporary scan code. Later, when custom labels are printed, each physical copy can receive a unique barcode such as `BK000001`.

---

## Current features

### Kid Kiosk

- Child-friendly kiosk UI
- Child selection using photo tiles
- Optional library-card barcode scanning
- Borrow books by scanning or typing a barcode
- Return books
- Search the catalogue
- View book details in a modal/lightbox
- Phone camera barcode scanning using a browser scanner fallback

### Admin

- Password-protected admin area
- Add books manually
- Edit book metadata
- Search books by title, author, illustrator, ISBN, barcode, category, synopsis, condition and borrower
- Paginated book list
- Upload or replace cover images
- Cache remote cover images locally
- Mark books as damaged / needing repair
- Soft-delete books from the catalogue
- Add and edit child profiles
- Upload child photos
- Bulk return borrowed books using checkboxes
- Scan-based bulk return fallback

### Data handling

- SQLite database stored outside the container in the `data` volume
- Cover images stored in `data/covers`
- Self-signed HTTPS proxy support for local phone camera scanning
- CSV import script for bulk loading books

---

## Repository structure

A typical ShelfQuest folder looks like this:

```text
shelfquest/
├── app/
│   ├── main.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── styles.css
├── data/
│   ├── library.db
│   ├── covers/
│   └── certs/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── import_books.py
└── README.md
```

The `data` folder is runtime data and should not be committed to Git.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/sheldondickinson/ShelfQuest.git
cd ShelfQuest
```

### 2. Create the data folder

```bash
mkdir -p data
```

On a QNAP NAS, a common location is:

```bash
/share/Container/shelfquest
```

### 3. Configure environment variables

Check `docker-compose.yml` and adjust values as required.

Common settings:

```yaml
environment:
  - LIBRARY_DB=/data/library.db
  - DEFAULT_LOAN_DAYS=7
  - ADMIN_PASSWORD=change-this-password
```

If using the HTTPS proxy, also check the certificate subject alternative names:

```yaml
- CERT_ALT_NAMES=DNS:shelfquest.local,DNS:localhost,IP:127.0.0.1,IP:192.168.1.50
```

Replace `192.168.1.50` with your NAS IP address.

### 4. Start the app

```bash
docker compose up -d --build
```

### 5. Check the containers

```bash
docker ps
```

You should see the ShelfQuest app container running. If HTTPS is enabled, you should also see the proxy container.

---

## Accessing ShelfQuest

### HTTP

```text
http://<your-nas-ip>:8123
```

Example:

```text
http://192.168.1.50:8123
```

### HTTPS

```text
https://<your-nas-ip>:8443
```

Example:

```text
https://192.168.1.50:8443
```

The built-in HTTPS option uses a self-signed certificate. Browsers will usually show a warning. Accept the warning for local home use, or replace it later with a trusted local certificate / reverse proxy configuration.

---

## Admin login

Admin is accessed using the small settings cog in the top-right of the ShelfQuest interface.

Set the admin password in `docker-compose.yml`:

```yaml
ADMIN_PASSWORD=change-this-password
```

For a public repository, do not commit a real household password. Use a placeholder in Git and override it locally.

---

## Basic usage

### Add children

1. Open ShelfQuest.
2. Tap the settings cog.
3. Enter the admin password.
4. Go to **Children**.
5. Add each child with:
   - name
   - library card barcode, for example `KID-PASCAL`
   - borrow limit
   - optional photo

### Add books manually

1. Go to **Admin → Add Book**.
2. Enter or scan the ISBN / barcode.
3. Fill in metadata such as title, author, illustrator, category and synopsis.
4. Add a cover URL or upload a cover image.
5. Save the book.

### Borrow a book

1. On the Kid Kiosk, select the child’s card.
2. Scan the book barcode using:
   - USB barcode scanner
   - phone camera scanner
   - manual typing
3. ShelfQuest records the loan if the book is available and borrow rules allow it.

### Return a book

Kid Kiosk supports simple single-book returns.

For parent-controlled batch returns:

1. Open **Admin**.
2. Go to **Bulk Returns**.
3. Select borrowed books using checkboxes.
4. Click **Return Selected**.

---

## Barcode strategy

ShelfQuest separates book identity from physical copy identity.

### ISBN-only phase

If no custom barcode is available yet, the ISBN can be used as the temporary scan code.

Example:

```csv
ISBN,Barcode,Qty,Title
9780143501763,,1,Where is the Green Sheep?
```

ShelfQuest treats the ISBN as the scannable code.

### Custom barcode phase

When labels are available, assign a unique barcode per physical copy.

Example:

```csv
ISBN,Barcode,Qty,Title
9780143501763,BK000001,1,Where is the Green Sheep?
9780143501763,BK000002,1,Where is the Green Sheep?
```

This allows true copy-level tracking.

### Physical duplicates before labels

If you own multiple copies but have not labelled them yet, use `Qty`.

Example:

```csv
ISBN,Barcode,Qty,Title
9780143501763,,2,Where is the Green Sheep?
```

ShelfQuest records that you own two physical copies, but only one ISBN-scannable copy exists until individual labels are created.

---

## CSV import

ShelfQuest includes an import script for loading a book catalogue from CSV.

### Expected CSV columns

```csv
ISBN,Barcode,Qty,Title,Author,Illustrator,Synopsis,Category,CoverURL
```

### Column behaviour

| Column | Purpose |
|---|---|
| `ISBN` | Title/edition identifier and fallback barcode |
| `Barcode` | Scannable physical copy code. If blank, ISBN is used temporarily |
| `Qty` | Number of physical copies owned |
| `Title` | Book title |
| `Author` | Author name |
| `Illustrator` | Illustrator name |
| `Synopsis` | Book description |
| `Category` | Shelf/category grouping |
| `CoverURL` | Remote or local cover image URL |

### Upload the CSV

Place the CSV in the container data folder:

```text
data/kids-library.csv
```

On QNAP, this is usually:

```text
/share/Container/shelfquest/data/kids-library.csv
```

### Back up the database first

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-import-$(date +%Y%m%d-%H%M).db
```

### Dry run

Run the importer in dry-run mode first:

```bash
docker exec -it shelfquest python /data/import_books.py /data/kids-library.csv --dry-run
```

The dry run reports how many books and scannable copies would be inserted or updated, without changing the database.

### Real import

```bash
docker exec -it shelfquest python /data/import_books.py /data/kids-library.csv
```

### Optional online lookup

If your CSV has missing metadata, the importer can attempt online lookup for missing values:

```bash
docker exec -it shelfquest python /data/import_books.py /data/kids-library.csv --lookup-missing
```

Use the normal import first. Use online lookup only when you deliberately want missing data filled from public book APIs.

---

## Checking database counts

After importing, you can check counts with:

```bash
docker exec -it shelfquest python - <<'PY'
import sqlite3
conn = sqlite3.connect('/data/library.db')

print('Books:', conn.execute('SELECT COUNT(*) FROM books').fetchone()[0])
print('Scannable copies:', conn.execute('SELECT COUNT(*) FROM book_copies').fetchone()[0])
print('Total owned qty:', conn.execute('SELECT SUM(owned_qty) FROM books').fetchone()[0])
print('Active loans:', conn.execute("SELECT COUNT(*) FROM loans WHERE status = 'active'").fetchone()[0])
PY
```

To list books where you own multiple physical copies:

```bash
docker exec -it shelfquest python - <<'PY'
import sqlite3
conn = sqlite3.connect('/data/library.db')

for row in conn.execute('''
    SELECT isbn, title, owned_qty
    FROM books
    WHERE owned_qty > 1
    ORDER BY title
'''):
    print(row[0], '|', row[1], '| Qty:', row[2])
PY
```

---

## Camera barcode scanning

ShelfQuest supports USB barcode scanners and phone camera scanning.

Phone camera scanning requires browser camera access. In most browsers that means HTTPS is required.

ShelfQuest uses a browser-based barcode scanning fallback so it can work on iPhone/Safari where native barcode detection is not reliably available.

If the scanner does not start:

1. Use the HTTPS URL, not HTTP.
2. Accept the self-signed certificate warning.
3. Allow camera permission.
4. Close and reopen the browser tab if the camera was previously left in a bad state.

---

## Backups

The important file is:

```text
data/library.db
```

Back it up before upgrades and imports:

```bash
cp data/library.db data/library-backup-$(date +%Y%m%d-%H%M).db
```

Cover images are stored in:

```text
data/covers
```

If cover uploads matter, back up the entire `data` folder.

---

## Upgrading

Before replacing app files:

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-upgrade-$(date +%Y%m%d-%H%M).db
```

Then copy the new app files over the existing folder without deleting `data`.

Rebuild:

```bash
docker compose down
docker compose up -d --build
```

After upgrading, hard-refresh the browser. On iPhone/iPad, close the tab and reopen it because Safari may cache old JavaScript/CSS.

---

## Security notes

ShelfQuest is intended for a trusted home LAN.

Do not expose it directly to the internet without adding proper authentication, TLS and reverse-proxy controls.

The admin password is basic protection for household use. It is not a full identity system.

---

## Development notes

The app was built quickly and iteratively to solve a practical home workflow problem:

- catalogue books
- let children borrow books
- stop books spreading through the house uncontrolled
- make returns easy for tired adults
- allow phone/Pi/PC access
- avoid running a full library management suite

The goal is not to replicate Koha or an enterprise library system. ShelfQuest is deliberately small, local and family-focused.

---

## Suggested future improvements

- Proper per-copy label generation
- Printable child library cards
- Better role/session handling
- Optional Home Assistant integration
- Reading streaks or child rewards
- Export catalogue and loan history
- Library open/closed schedule
- Better mobile install/PWA behaviour
- Trusted local certificate workflow
