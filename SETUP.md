# Setup

Everything needed to go from zero to a working worklist. Roughly 20 minutes,
most of it waiting on Google.

The three steps that trip people up have **no system prompt** and fail quietly,
so they're first: Gatekeeper, Full Disk Access, and billing.

---

## 1. Open the app once (Gatekeeper)

The app is unsigned. There's no $99/yr Apple Developer cert behind it. macOS
will refuse a plain double-click on first launch.

**Right-click the app → Open → Open.** Once per install; normal double-clicks
work afterward.

If macOS says the app "is damaged", it was quarantined on download:

```sh
xattr -dr com.apple.quarantine "/Applications/Beli Staging.app"
```

## 2. Grant Full Disk Access

Beli reads the Photos library's database directly (via `osxphotos`), which macOS
gates behind **Full Disk Access**.

**There is no prompt for this.** Nothing will pop up asking. You have to add the
app by hand:

> System Settings → Privacy & Security → Full Disk Access → **+** → select
> `Beli Staging.app` → make sure the toggle is **on** → reopen Beli.

If it's not granted, the app tells you so and shows its own path. This is *not*
the "Photos" permission. That one governs a different API and does nothing here.

> Re-granting after an update is expected: the app is unsigned, so macOS may see
> a rebuilt version as a different app.

## 3. Get a Google Places API key (with billing on)

Matching goes through **Places API (New)**. Google requires a billing account
even though real usage lands in the free tier.

1. Go to <https://console.cloud.google.com/> and create a project.
2. **Enable billing** on it (Billing → link an account). Without this every
   lookup fails.
3. Enable **Places API (New)**: APIs & Services → Library → search for it →
   Enable. Note: "Places API" and "Places API (New)" are *different products*;
   you want the New one.
4. APIs & Services → Credentials → Create credentials → API key. Copy it.
5. Recommended: restrict the key to Places API (New) so a leak can't cost you.

Costs: each saved place and each photo-visit is one lookup, and results are
cached for 90 days, so re-runs are free. A few hundred places sits inside
Google's monthly free allowance.

If the key is wrong, billing is off, or the API isn't enabled, Beli says so in
plain language rather than dying, but it can't run until it's fixed.

## 4. Paste the key into config.toml

First launch creates `~/Library/Application Support/beli-tool/` containing a
template `config.toml` and an empty `inbox/`.

Open `~/Library/Application Support/beli-tool/config.toml` and replace
`PASTE_YOUR_KEY_HERE` with your key.

Worth setting while you're in there:

```toml
# Ignore photos older than this. Without it, every run walks your whole library.
since = "2024-01-01"
# Photo visits matched per run, newest first. Each one costs a lookup.
max_visits = 300
```

### Optional: mirror adds into Obsidian

Set `obsidian_log` to a note path and every place you tap **Added ✓** on gets
appended there as a table row: date, place, rating, visit date, address, list.
The note is created on first write, with the frontmatter and table your vault
already uses.

```toml
obsidian_log = "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/YOUR_VAULT/08-Lookup/beli-log.md"
```

The ledger stays the source of truth; this is the readable copy that outlives it.
Writes are best-effort: if the vault is missing or mid-sync, the add still
counts and only the log line is skipped.

## 5. Export your Google Maps saved lists

1. Go to <https://takeout.google.com/>.
2. **Deselect all**, then select only **Maps (your places)**.
3. Export, wait for the email, download the zip.
4. Find the `.csv` files (Want to go, Favorites, Starred places…) and drop them
   into `~/Library/Application Support/beli-tool/inbox/`.

The filename becomes the list name, so keep them meaningfully named. Photos-only
runs work fine if you skip this: the inbox can stay empty.

## 6. Run it

Open **Beli Staging.app**. It scans, then shows a dialog with a URL like
`http://192.168.1.42:8000/?t=AbC123`. Open that on your phone (same Wi-Fi).

The `?t=` token is required: it's what stops anyone else on a coffee-shop
network from browsing your photos and location history. It changes every run.

For each card: rate it, tap **Copy name & open Beli**, paste, then tap
**Added ✓** so it never comes back. **Rescan** re-reads photos and CSVs without
a restart. Quit the app when you're done.

From a terminal instead: `beli-tool run`.

---

## When something's wrong

| What you see | What it means |
|---|---|
| Nothing happens on double-click | Gatekeeper: right-click → Open (step 1). |
| "Beli needs Full Disk Access" | Step 2. There is no prompt; add it manually. |
| "Google rejected the Places request" | Key wrong, billing off, or Places API (New) not enabled (step 3). |
| "rate-limiting or you're out of quota" | Over the free tier or hitting limits: check the quota page. |
| "Add your Google Places API key to…" | The template key is still in `config.toml` (step 4). |
| 0 saved places found | No `.csv` in `inbox/`, or they're the wrong Takeout export (step 5). |
| Phone can't load the URL | Different Wi-Fi, or the `?t=` token is missing/stale. |
| A visit matched the wrong restaurant | Tap Skip. GPS drifts indoors; the nearest food hit isn't always right. |
| Places under "Couldn't match" | No restaurant found there: a home-cooked meal, a park, a bad GPS fix. |

**Still stuck? Read the log.** Every run appends to
`~/Library/Application Support/beli-tool/beli-tool.log`: what the config was, how
many places were found, what you added or skipped, and any error in full. The
.app is windowed and has no console, so this is the only record of what it did.

```sh
tail -50 ~/Library/Application\ Support/beli-tool/beli-tool.log
```

It never contains your API key. It rotates at ~500KB, keeping 2 old copies.

**Where things live**, all under `~/Library/Application Support/beli-tool/`:

- `config.toml`: your key and settings
- `inbox/`: Takeout CSVs
- `ledger.sqlite`: what you've handled + the Places cache
- `ledger.sqlite.bak`: the previous run's copy, made at every startup
- `beli-tool.log`: what happened, every run

Plus, if `obsidian_log` is set, the vault note you pointed it at.

Delete a row from `ledger.sqlite` to make a place show up again. Restore the
`.bak` if you skip-spree something you wanted.
