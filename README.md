# Beli staging tool

Aggregates Google Maps saved lists (→ Want to Try) and GPS-stamped photos
(→ Been) into a phone-friendly worklist for fast manual entry into Beli.
Matching uses each photo's embedded GPS coordinate (not image content) via the
Google Places API (New). A local SQLite ledger keeps it incremental — each run
shows only places you haven't handled yet.

## One-time setup

1. In Google Cloud Console, enable **Places API (New)** and create an API key
   (Maps Platform → Keys & Credentials). The free tier is plenty for personal use.
2. `cp config.example.toml ~/beli-tool/config.toml` and paste your key.
3. `python3 -m venv .venv && . .venv/bin/activate && pip install -e .`
4. Grant Photos access when macOS prompts on first run.

## Each run

1. Export Google Takeout → "Maps (your places)"; unzip the `Saved/*.csv` files
   into `~/beli-tool/inbox/`.
2. `beli-tool run`
3. Open the printed `http://<ip>:8000` URL on your phone (same Wi-Fi).
4. Rank each Been place (😍/😐/😞), tap "Copy & open Beli", paste, add, then
   tap "Added ✓". Tap through Want to Try the same way.

The final tap into Beli is manual by design (Beli has no import/API).
