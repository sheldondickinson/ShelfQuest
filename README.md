# ShelfQuest v0.2.0

This update improves the real-world flow after phone-camera testing.

## Added / changed

- Camera scanner now force-releases prior camera sessions before opening a new one.
- Repeated phone scans in the same browser tab should now work more reliably, especially on iOS Safari.
- Kid Kiosk now has separate action views: Borrow, Return, Find, Reading.
- Admin now has separate action views: Books, Add Book, Children, Bulk Returns.
- Saving a book edit closes the edit form and returns to the book list.
- Saving a child edit closes the edit form and returns to the children list.
- Added admin-only bulk returns.

## Bulk returns

Bulk returns are only available after Admin unlock. Kids still have the normal single-book return flow in the Kid Kiosk, but the batch return queue is not exposed there.

## Upgrade

1. Back up the database:

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v020-$(date +%Y%m%d-%H%M).db
```

2. Copy the contents of `shelfquest_v020/` over `/share/Container/shelfquest/`.

Do not delete the `data` folder.

3. Rebuild:

```bash
cd /share/Container/shelfquest
docker compose down
docker compose up -d --build
```

4. Hard refresh the browser.

On desktop: `Ctrl + F5`.

On iPhone/iPad: close the tab, reopen `https://<qnap-ip>:8443`, and accept the self-signed certificate warning if prompted.
