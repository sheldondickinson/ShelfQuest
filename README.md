# ShelfQuest v0.1.6

Adds the first real admin maintenance features:

- Edit book metadata from the Admin UI
- Search across title, author, illustrator, synopsis, category, ISBN, barcode, status, condition notes and borrowed-by child
- Mark a book copy as `Damaged, needs repair`
- Mark a damaged book as repaired
- Delete/hide a book from the catalogue without breaking historical loan records
- More child-like Kid Kiosk UI

## Upgrade notes

1. Back up `/share/Container/shelfquest/data/library.db` first.
2. Copy these files over the existing `/share/Container/shelfquest` folder.
3. Do not delete the `data` folder.
4. Rebuild and restart:

```bash
cd /share/Container/shelfquest
docker compose down
docker compose up -d --build
```

The app performs lightweight SQLite migrations on startup. It adds:

- `books.deleted_at`
- `books.updated_at`
- `book_copies.condition_status`
- `book_copies.updated_at`

Deleted books are soft-deleted: they disappear from the catalogue, but historical loan/event records remain intact.

## Importer

The v0.1.4 importer is included. It supports:

`ISBN,Barcode,Qty,Title,Author,Illustrator,Synopsis,Category,CoverURL`

Duplicate ISBN rows with blank `Barcode` are counted into `Qty` rather than creating ambiguous duplicate scan codes.


## v0.1.6 additions

- Kid Kiosk title changed to ShelfQuest.
- Kids can choose their library card from a dropdown or scan their card.
- Admin edit screen can upload a local cover image. Images are stored in `/data/covers` and served from `/covers/...`.
- Admin can copy/cache remote `CoverURL` images into the NAS-hosted covers folder.
- Kid Kiosk now has a book search with clickable result cards and a detail lightbox.
