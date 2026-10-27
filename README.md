# Swarnam4U
Kerala gold, silver and platinum rate website, with a browser-based rate calculator, historical trends and a daily poster generator.
Public site: https://swarnam4u.onrender.com

The repository's GitHub Pages setting is not enabled; the public site is served by its separate hosting configuration.

Pages: `index.html` (current rates), `trends.html`, `calculator.html`, `about.html`, `contact.html`.
Shared files: `assets/site.css`, `assets/site.js`. Data: `data/rates.json`.

## How rates update (no manual step)
`.github/workflows/update.yml` runs `scripts/fetch_rates.py` every 10 minutes (GitHub may delay scheduled starts). It writes the rates snapshot atomically and is intended to commit only meaningful rate/history/spot changes, avoiding timestamp-only redeploys. Overlapping runs are blocked (`concurrency`).
If a fetch fails, the previous file is kept and the run is marked failed (GitHub emails the repo owner).
Only validated fetched values and explicitly labelled calculations are stored. History contains actual observed daily snapshots; gaps are not filled with invented values.

## How rates are fetched (same method as the Asian Jewellery project)
Fetching runs **server-side**, never relying on the visitor's browser:
1. **GitHub Action** (`scripts/fetch_rates.py`, every 10 min) reads AKGSMA (`22K916 (1gm)`, `18K750 (1gm)`, `Silver (1gm)` and the rate date). If AKGSMA is unreachable it uses LiveGold Kerala (which relays the same board rate). Values are validated (plausible range, 18K/22K ratio, no >15% jump).
2. **24K and 14K are calculated** from the 22K board rate (22K x 24/22, 22K x 585/916) and labelled "calculated". AKGSMA publishes no 24K, 14K or platinum.
3. **Platinum** has no AKGSMA rate: it comes from Goodreturns/BankBazaar pages and carries an amber tag.
4. **Browser:** on open it shows the last known rates instantly and re-checks live (Worker API if configured, else AKGSMA/LiveGold via public relays), replacing them as soon as newer ones arrive. The Refresh button repeats this.
5. `data/rates.json` keeps the last saved snapshot so the site can show known rates while a new refresh is attempted. Each rate's own date/source should be checked, not inferred from the file timestamp alone.

## Fastest fetch (optional)
Deploy `worker/rates-worker.js` (adds a `?api=rates` JSON endpoint that parses AKGSMA server-side) to Cloudflare Workers and set `WORKER` in `assets/site.js` (see `worker/README.md`).

## One-time setup
1. Confirm the separate host serving `https://swarnam4u.onrender.com` deploys the `main` branch and publishes the site files from the repository root.
2. Repo > Settings > Actions > General > Workflow permissions: **Read and write**.
3. Run `python scripts/fetch_rates.py --check` locally (or Actions > "Update rates" > Run workflow) and compare the
   printed values with akgsma.com. Adjust `PATTERNS` in the script if they differ.
4. Confirm akgsma.com permits automated access. The fetcher checks `robots.txt` before requesting the primary AKGSMA page and uses fallback sources when needed.

## YouTube Shorts automation for `@SWARANAM4U`

Channel: https://www.youtube.com/@SWARANAM4U

The scheduled `Build Swarnam4U Shorts` workflow refreshes and validates today's AKGSMA board before generating English and Malayalam vertical videos for the morning (10:30 IST), midday (13:00 IST) and evening (17:00 IST) slots. Build starts are scheduled for 10:10, 12:30 and 16:30 IST to leave time for the runner. If GitHub Actions starts too late, the uploader refuses the missed slot rather than publishing late.

Every MP4 is checked with `ffprobe` for H.264 video at 1080×1920/30 fps/yuv420p, AAC audio at 48 kHz, valid duration and reasonable file size. A successful build attaches MP4, MP3, card PNG, preflight report and manifest as an Actions artifact. The workflow also keeps the real day-over-day movement from the saved published rate; it does not invent missing previous-day values.

### Safe YouTube modes

- `build_only` is the manual default: generate the files and artifact only; do not call YouTube.
- `private_test` uploads an English/Malayalam pair with a visible `[PRIVATE TEST]` marker. Both videos remain **Private** and have no `publishAt` time. Use this to check actual upload permission, Malayalam title/description, pronunciation, and playback in Studio.
- `schedule` uploads the selected pair as private and asks YouTube to release it at the selected target time. It refuses if the target is less than five minutes away or has passed.
- Daily scheduled publishing remains disabled unless the Actions repository variable `YOUTUBE_AUTO_PUBLISH` is set to `true`. A manual `private_test` or `schedule` selection is a one-run explicit opt-in that can be used while the daily variable is unset.
- The uploader verifies that the authorized channel matches `@SWARANAM4U`, checks recent uploads for exact or same-slot duplicates, requires both valid MP4s, retries YouTube insert requests, and records an `upload-report.json` with video URLs or the failure reason.

### One-time YouTube OAuth setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen and create an OAuth client of type **Desktop app**. Download its JSON file to your Downloads folder. The Google account used during the browser authorization must own or manage `@SWARANAM4U`.
3. From the repository root on Windows, install the helper dependency and run it with the actual JSON filename:

   ```powershell
   py -m pip install -r requirements-youtube-auth.txt
   py scripts/authorize_youtube.py "$env:USERPROFILE\Downloads\client_secret_....json"
   ```

   This opens Google's authorization page and saves the refresh token outside the repository under your user profile, by default in `%APPDATA%\Swarnam4U\youtube-refresh-token.txt`. It does not upload any video. Do not commit the OAuth JSON or token file.
4. In repository **Settings → Secrets and variables → Actions → Secrets**, add:
   - `YOUTUBE_CLIENT_SECRET_JSON`: the full contents of the downloaded OAuth client JSON file.
   - `YOUTUBE_REFRESH_TOKEN`: the contents of the saved refresh-token file. On Windows, use `Get-Content "$env:APPDATA\Swarnam4U\youtube-refresh-token.txt" -Raw` locally to display it for copying into the GitHub secret form. Never paste it into chat/issues.
5. Under **Settings → Secrets and variables → Actions → Variables**, set `YOUTUBE_EXPECTED_CHANNEL_HANDLE` to `@SWARANAM4U` (the workflow defaults to this value if absent).
6. In Actions, run **Verify YouTube connection**. It checks OAuth access, the expected channel, and uploads-playlist access without uploading a video.
7. Run **Build Swarnam4U Shorts**, choose an available slot, and set `publish_mode=private_test`. Confirm both items in [YouTube Studio](https://studio.youtube.com/) are **Private**, that the Malayalam title and description use Malayalam script, and that the metadata/rates/audio are right.
8. Only after that verification, set `YOUTUBE_AUTO_PUBLISH=true` to enable daily scheduled uploads. If you prefer manual releases, leave the variable unset and explicitly select `schedule` for each upload.

**OAuth lifetime:** Google documents that refresh tokens for external test users can expire after seven days when the consent screen remains in **Testing**. For unattended daily use, review [Google's OAuth publishing-status and refresh-token guidance](https://developers.google.com/identity/protocols/oauth2/) and complete any production/verification steps required for your project's YouTube scopes. Do not rely on a Testing-mode token for long-term unattended runs.

Scheduled workflows on public repos are paused after 60 days without repo activity; re-enable under Actions if that happens.
Local preview: `python -m http.server 8000`.

## Asian Jewellery rate poster (`poster.html`)
Overlays today's date and a rate table on one of the 10 supplied Asian Jewellery designs (`assets/posters/design-01..10.png`), in the browser (Canvas, no backend). Exports a PNG at the design's own pixel size (about 1028 x 1530), never stretched.
- **Daily rotation:** Design 1 on `anchorDate` (21 Oct 2026, IST), then 2, 3 ... 10, then back to 1. Pure IST calendar-date maths: same date = same design, refresh/redeploy never changes it. Design order = the order of files inside `asianposter.zip`. `?design=N` on the URL previews a specific design.
- **Per-design settings:** `data/poster-templates.json` holds each design's image path, panel/label/price/date colours, and the shared table layout (fractions of image width/height, so differing image sizes work).
- Rows: 22K 916, 18K 750 (AKGSMA board rates), 14K and 9K (calculated from 22K by purity, rounded to nearest Rs 10), silver 1 g / 10 g. Pavan = 8 g. "UNCHANGED" appears only when the data has a previous rate that is equal.
- The date pill is today's IST date. "RATES UPDATED" is the real rate timestamp; if older than 24 h it reads "LAST UPDATED" and the page shows a stale warning.
- Invalid or missing rates disable the poster; previous valid data is kept.
- Own rates: `{"overrides":{"14K":8570,"9K":5530}}` in `data/poster-config.json` (keys: 22K, 18K, 14K, 9K, SILVER).
- Share: Web Share API with the PNG where supported (choose WhatsApp > Status); otherwise the PNG downloads and a wa.me message opens. WhatsApp Status is never posted automatically.
- Tests: `node tests/poster.test.js`.

## Trends page (`trends.html`) - gold and silver only
- Series: Gold 22K 916, Gold 24K 999, Silver 999, Silver 925. Real daily snapshots are stored in `data/rates.json` under `series` (one point per day, added by `scripts/fetch_rates.py` on every run; nothing is back-filled or invented). Existing history (7 days of 22K) was kept; 24K history is the 22K record x 24/22 and is labelled "calculated". Silver has 1 recorded day so far, so its chips stay disabled ("needs more days") until 2+ days exist.
- Ranges 1 Week / 1 Month / 3 Months / 6 Months / 1 Year / 5 Years / All (plus From/To dates) filter the real records. If the range reaches back further than the records, the page says so instead of filling the gap.
- Select several series to compare. Gold and silver together are drawn as % change in the range (their prices are on different scales). Hover/touch shows the date and exact rate of each series.
- Platinum is not shown on this page (it is still on the home page and calculator).

## Favicon
Transparent crown-dollar symbol: `favicon.ico`, `assets/icons/favicon-16/32/48.png`, `icon-192/512.png`, `apple-touch-icon.png` (iOS needs a solid tile), referenced in every page's `<head>`.

## 5-year history (one-time backfill)
Actions > **Backfill history** > Run workflow (defaults 2021-10-21 to 2026-10-21). It reads GoodReturns' past-day Kerala
rate once per day (about 1,800 requests, 30-60 min), stores only prices actually returned, skips empty days and can be
re-run to resume. After it finishes, the **5 Years** button fills in. Until then the page says how far back the records go.
`fetch_rates.py` keeps up to 3,000 days per series, so history keeps growing every day.

## Upcoming-rate forecast on the trend graph
Toggle "Show upcoming rate (forecast)" and pick Next 1 Week / 1 Month / 3 Months. The dashed line is a damped trend fitted to
the last ~120 recorded days; the shaded band is the 90% likely range from normal day-to-day movement. It needs at least 10
recorded days, is labelled as an estimate everywhere, and is never written to `data/rates.json`.
