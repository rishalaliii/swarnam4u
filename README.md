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

The scheduled `Build Swarnam4U Shorts` workflow refreshes and validates the current AKGSMA board, then generates English and Malayalam vertical videos for the morning (10:30 IST), midday (13:00 IST) and evening (17:00 IST) slots. Build starts are scheduled for 10:10, 12:30 and 16:30 IST to leave time for runners to start and check today's board. GitHub Actions can be delayed; if a slot is less than five minutes away or has passed, the uploader refuses the upload instead of publishing late.

The renderer validates each MP4 with `ffprobe`: H.264 video at 1080×1920/30 fps/yuv420p, AAC audio at 48 kHz, valid duration and minimum file size. A passing build attaches MP4, MP3, card PNG, preflight report and manifest as a downloadable Actions artifact.

### Safe upload modes

- `build_only` is the manual default: generate the files and artifact only; do not contact YouTube.
- `private_test` uploads an unmistakably labelled English/Malayalam pair with **Private** visibility and no scheduled publish time. Use this to verify real OAuth and inspect metadata in Studio.
- `schedule` uploads the pair as private and asks YouTube to publish at the selected slot's target time. Scheduling is allowed only when the target is in the future with at least five minutes remaining.
- Scheduled daily publishing stays disabled until the Actions repository variable `YOUTUBE_AUTO_PUBLISH` is set to `true`. A manual `private_test` or `schedule` selection is a one-run explicit opt-in and does not require that daily variable, but still requires the OAuth secrets and current preflight.
- The uploader verifies the OAuth account matches `@SWARANAM4U`, checks recent uploads for exact or same-slot duplicates, requires both valid MP4s, uses bounded upload retries, and writes an `upload-report.json` containing video URLs or the failure reason.

### One-time YouTube OAuth setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select a project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen and create an OAuth client of type **Desktop app**. Download its JSON file. The account used in the authorization browser must own or manage `@SWARANAM4U`.
3. From the repository root on Windows, install the local setup dependencies and run the helper. Replace the sample JSON path with the exact file you downloaded:

   ```powershell
   py -m pip install -r requirements-youtube-setup.txt
   py scripts/create_youtube_refresh_token.py --client-secrets "$HOME/Downloads/client_secret.json"
   ```

   The helper requests `youtube.upload` and `youtube.readonly`, confirms the account resolves to the expected channel, and only then prints a refresh token. If channel verification fails, it prints no token. Keep the client JSON and token local; never paste either into chat or commit them.
4. In repository **Settings → Secrets and variables → Actions → Secrets**, add:
   - `YOUTUBE_CLIENT_SECRET_JSON`: the complete contents of the downloaded OAuth client JSON.
   - `YOUTUBE_REFRESH_TOKEN`: the refresh token printed by the local helper.
5. In repository **Settings → Secrets and variables → Actions → Variables**, set `YOUTUBE_EXPECTED_CHANNEL_HANDLE` to `@SWARANAM4U` (the uploader uses this default if the variable is absent).
6. In Actions, run **Verify YouTube connection**. This checks account identity and uploads-playlist access without uploading a video.
7. Run **Build Swarnam4U Shorts**; choose a slot that has current board rates, then choose `private_test`. Inspect both videos in [YouTube Studio](https://studio.youtube.com/). Check the English title/description, Malayalam-script title/description, prices, pronunciation, video quality and visibility. The test videos will remain private.
8. Only after the private test succeeds, set `YOUTUBE_AUTO_PUBLISH=true` to enable the daily scheduled uploads. Leave it unset if you prefer to manually select each `schedule` run.

**OAuth lifetime:** Google documents that refresh tokens issued to external test users while the consent screen is in **Testing** can expire after seven days. For reliable unattended daily publishing, review Google's [OAuth publishing-status guidance](https://support.google.com/cloud/answer/15549945?hl=en) and complete any verification/production steps required for the project's YouTube scopes. Do not assume a testing-mode refresh token will last indefinitely.

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
