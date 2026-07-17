# Beli staging tool

Aggregates Google Maps saved lists (→ Want to Try) and GPS-stamped photos
(→ Been) into a phone-friendly worklist for fast manual entry into Beli.
Matching uses each photo's embedded GPS coordinate (not image content) via the
Google Places API (New). A local SQLite ledger keeps it incremental — each run
shows only places you haven't handled yet — and Places responses are cached in
the same file, so re-runs don't re-query (or re-pay for) what Google already
answered.

Set `since` in `config.toml` to bound how far back the Photos scan reaches;
without it, every run walks your whole library. Set `obsidian_log` to mirror
every add into an Obsidian note as a running history.

## Install

**As an app (no terminal):** download from the
[release page](https://kristenharim.github.io/beli-tool/), unzip, and drag
**Beli Staging.app** to Applications. First launch: right-click → Open (it's
unsigned). Double-clicking it runs the same thing as `beli-tool run` below and
shows the phone URL in a dialog.

**From source:** `python3 -m venv .venv && . .venv/bin/activate && pip install -e .`

## One-time setup

**→ [SETUP.md](SETUP.md)** walks the whole thing: the Gatekeeper first-open, the
Full Disk Access grant (no prompt — you add it by hand), the Places API key and
billing, the Takeout export, and a troubleshooting table.

First run creates `~/Library/Application Support/beli-tool/` with a template
`config.toml` and an `inbox/` folder, then tells you to add your key.

> **Upgrading from 0.1.0?** Config and ledger moved to
> `~/Library/Application Support/beli-tool/`. Copy your old `config.toml` and
> `ledger.sqlite` in, or just paste your key into the new template — you'll only
> lose the record of which places you'd already handled.

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

**Rescan** (top right) re-reads photos and CSVs in place — no need to quit and
reopen after dropping in a new export. Cached lookups make it cheap.

The final tap into Beli is manual by design (Beli has no import/API).
