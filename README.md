# ShelfQuest v0.2.1

Small UI and parent workflow polish.

## Changes

- Replaces the old dark title bar with the purple/blue ShelfQuest hero header at the very top.
- Removes the large Kid Kiosk/Admin/Refresh buttons.
- Adds a subtle settings cog in the top-right corner to enter Admin.
- Changes the Admin heading action to **Kiosk**, which locks Admin and returns to the Kid Kiosk.
- Updates Admin Bulk Returns to list all currently borrowed books with checkboxes, including who has each book.
- Keeps the scan-based bulk return queue available behind a collapsible section.

## Upgrade

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v021-$(date +%Y%m%d-%H%M).db
docker compose down
docker compose up -d --build
```

After copying the v0.2.1 files over the existing app folder, hard refresh the browser. On iPhone/iPad, close and reopen the tab if Safari holds onto the old JS/CSS.
