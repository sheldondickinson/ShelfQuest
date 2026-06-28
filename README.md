# ShelfQuest v0.1.9 - Safari camera barcode fallback

This version keeps the self-signed HTTPS proxy from v0.1.8 and changes camera barcode scanning so iPhone/iPad Safari can use a JavaScript scanner fallback when the native `BarcodeDetector` API is unavailable.

## What changed

- Native `BarcodeDetector` still used where available.
- Safari/iOS fallback added using ZXing Browser from jsDelivr CDN.
- Same scan buttons and fields remain unchanged.

## Important

The fallback library is loaded from:

```text
https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/umd/zxing-browser.min.js
```

Your phone needs internet access the first time the scanner loads. A later version can bundle the library locally if required.

## Upgrade

```bash
cd /share/Container/shelfquest
cp data/library.db data/library-before-v019-$(date +%Y%m%d-%H%M).db
docker compose down
docker compose up -d --build
```

Then open:

```text
https://<qnap-ip>:8443
```

Accept the self-signed certificate warning if prompted and allow camera access.
