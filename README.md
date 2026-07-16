# Beli staging tool

Aggregates Google Maps saved lists (→ Want to Try) and GPS-stamped photos
(→ Been) into a phone-friendly worklist for fast manual entry into Beli.
Matching uses each photo's embedded GPS coordinate (not image content) via the
Google Places API (New). A local SQLite ledger keeps it incremental — each run
shows only places you haven't handled yet.

## Install

**As an app (no terminal):** download from the
[release page](https://kristenharim.github.io/beli-tool/), unzip, and drag
**Beli Staging.app** to Applications. First launch: right-click → Open (it's
unsigned). Double-clicking it runs the same thing as `beli-tool run` below and
shows the phone URL in a dialog.

**From source:** `python3 -m venv .venv && . .venv/bin/activate && pip install -e .`

## One-time setup

First run creates `~/Library/Application Support/beli-tool/` with a template
`config.toml` and an `inbox/` folder, then tells you to add your key.

1. In Google Cloud Console, enable **Places API (New)** and create an API key
   (Maps Platform → Keys & Credentials). The free tier is plenty for personal use.
2. Paste your key into `~/Library/Application Support/beli-tool/config.toml`.
3. **Grant Full Disk Access** to Beli Staging.app (or your terminal, if running
   from source): System Settings → Privacy & Security → Full Disk Access. This is
   required to read the Photos library and has **no automatic prompt** — you add
   the app by hand. Without it the app can't see your photos.

## Building the .app yourself

`pip install pyinstaller && pyinstaller beli-tool.spec --noconfirm` → `dist/Beli Staging.app`.
Pushing a `v*` tag builds and publishes it via GitHub Actions (`.github/workflows/release.yml`).

## Each run

1. Export Google Takeout → "Maps (your places)"; unzip the `Saved/*.csv` files
   into `~/Library/Application Support/beli-tool/inbox/`.
2. `beli-tool run`
3. Open the printed `http://<ip>:8000/?t=<token>` URL on your phone (same Wi-Fi).
   The token in the URL keeps others on the network out; open the whole URL.
4. Rank each Been place (😍/😐/😞), tap "Copy & open Beli", paste, add, then
   tap "Added ✓". Tap through Want to Try the same way.

The final tap into Beli is manual by design (Beli has no import/API).
