# ShelfQuest v0.2.3

Compact heading update.

## Changes

- Significantly reduced the height of the purple/blue ShelfQuest heading.
- Kept the gradient, ShelfQuest title, tagline, emojis, settings cog and version marker.
- Improved mobile spacing so the header uses less vertical screen real estate.

## Upgrade

Copy this folder over your existing ShelfQuest folder without deleting `data`, then rebuild:

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v023-$(date +%Y%m%d-%H%M).db
docker compose down
docker compose up -d --build
```

On iPhone/iPad, close the tab and reopen it to clear cached CSS/JS.
