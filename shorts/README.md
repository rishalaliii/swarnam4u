# Swarnam4U cloud Shorts pipeline

This branch adds a first cloud-generated bilingual video stage. It does not change the live website or its existing rate updater.

## What this branch does
- Checks the current AKGSMA board date in Asia/Kolkata.
- Checks that the saved 22K/916, 18K/750 and silver 999 values and their record dates match the live board.
- Generates one English and one Malayalam vertical video per run.
- Adds the publication date, source label, rates, and the exact website text `swarnam4u.onrender.com`.
- Generates neural voice tracks and renders 1080×1920 H.264/AAC MP4s.
- Gold cards show both the per-gram board rate and the calculated 8-gram/1-pawan total with Indian-style rupee grouping.
- The voiceover includes both 8-gram gold totals and clarifies that those totals are calculated from the per-gram prices. Scripts are concise, use a modestly faster natural voice rate, and stop if narration exceeds 55 seconds.
- Malayalam card labels avoid the unsupported decorative bullet glyph that previously appeared as square boxes.
- Malayalam cards use Noto Sans Malayalam with RAQM shaping; Latin brand/URL/date/source strings use DejaVu Sans, so missing Latin glyphs cannot silently become square boxes.
- The workflow checks RAQM is enabled and the font family selected for Malayalam is actually Noto Sans Malayalam; it fails rather than falling back silently.
- Checks generated dimensions and file size, then saves MP4, PNG, MP3, and a manifest as a workflow artifact for review.

## Target slots
The cloud starts are scheduled for 10:10, 12:45 and 16:45 India time. The morning job is deliberately after AKGSMA publishes its board around 10:00; it refreshes the workflow's working copy from the live source before validating. The morning video is scheduled for 10:30 because current-day rates cannot be fetched and rendered before the board is published. Midday/evening target 13:00 and 17:00. GitHub Actions can be delayed; no exact-minute guarantee is possible.

If all three runs succeed, that is six generated clips per day: three English and three Malayalam.

## How to test after the pull request is merged
1. Open the repository's **Actions** tab.
2. Run **Swarnam4U Shorts Preflight** first.
3. Then run **Build Swarnam4U Shorts**, select a slot, and inspect its artifact.
4. Listen to both audio tracks, check Malayalam shaping/pronunciation and the full-screen text, and view the MP4 on a phone before using the videos.

The scheduled build only runs once the workflow is present on the default branch. It is intentionally not enabled for YouTube uploading yet.

## Current limitations
- The uploader has explicit `private_test` and `schedule` modes. Scheduled publishing remains disabled by default; daily uploads happen only if the repository Actions variable `YOUTUBE_AUTO_PUBLISH` is explicitly set to `true` and both OAuth secrets are present. A private test run leaves its videos private and does not set `publishAt`.
- English and Malayalam descriptions are localized, include the AKGSMA source, the latest-rates website link, and the channel link https://www.youtube.com/@SWARANAM4U.
- The current board date and saved published-rate values must pass preflight. When AKGSMA has not published today's board rates, generation stops; no stale rates are published.
- The video displays only the board's published 22K/916, 18K/750 and silver 999 values. It does not show 925 silver because AKGSMA has been showing it as unavailable.
- Calculated 24K/14K prices, platinum fallbacks, and estimated values are deliberately excluded from these Shorts.
- Neural TTS availability, Malayalam pronunciation, final aesthetics and end-to-end video playback still need review from a successful live workflow artifact.
- YouTube setup still requires enabling YouTube Data API v3 for a Google Cloud project, creating an OAuth Desktop-app client, running `scripts/create_youtube_refresh_token.py`, and securely adding two Actions Secrets. See the repository README for the step-by-step process and the seven-day refresh-token warning for OAuth consent screens left in Testing.
- Only after a successful artifact review should the repository Actions variable `YOUTUBE_AUTO_PUBLISH=true` be added. Leave the variable absent otherwise. Never paste credentials or refresh tokens into issues or chat.
- The uploader schedules the English and Malayalam pair for the slot's target time, and checks the latest 50 entries in the channel's uploads playlist to avoid re-uploading matching titles. Review this behavior on a test channel before production.

The publish gate stays disabled until those checks are completed. Do not edit snapshot timestamps or copy old prices forward to bypass preflight.


## Day-over-day change and YouTube title
- The title uses the published 22K/916 rate change per gram versus the saved previous-day value. The title includes the date, planned slot time in 24-hour IST, direction (up/down/no change), and the amount when available.
- English title example: `Today's Gold Rate | 27 Oct 2026 | 10:30 IST | UP ₹50/g vs Yesterday #Shorts`.
- Malayalam title example: `ഇന്നത്തെ സ്വർണ്ണവില | 27 Oct 2026 | 10:30 IST | ഇന്നലെയേക്കാൾ ₹50/g വർധിച്ചു #Shorts`.
- 22K, 18K, and silver cards display their own previous-day change where a previous value exists. Narration calls out the main 22K movement.
- Missing previous values show a comparison-unavailable label; no amount is fabricated. If a previous snapshot is explicitly dated and not the prior calendar date, the comparison is treated as unavailable.
- The rate updater now preserves `yesterday_date` on refresh so future comparisons can verify the prior snapshot date.


## Title hashtags
- Every generated/uploaded title includes the relevant hashtags `#KeralaGoldRate #Shorts`.
- Titles preserve the language-specific gold-rate name, full date, 24-hour IST slot time, and previous-day movement.
- The title builder tests every movement state and enforces YouTube's 100-character maximum without cutting off the hashtags.
- The hashtags are relevant topic labels, not a guarantee of maximum reach; review audience retention and traffic sources in YouTube Analytics to tune them over time.


## Malayalam-only YouTube title localization
For Malayalam uploads only, the title's name, month/date, time label and price-movement phrase are in Malayalam script (for example: `ഇന്നത്തെ സ്വർണ്ണവില | 27 ഒക്ടോബർ 2026 | 10:30 | ഇന്നലെയേക്കാൾ ₹50/ഗ്രാം വർധന #KeralaGoldRate #Shorts`). The existing English title format is unchanged. The English hashtags are retained intentionally for searchable topic keywords. When needed, the title drops the day-part or shortens the movement phrase while staying within YouTube's 100-character limit.
