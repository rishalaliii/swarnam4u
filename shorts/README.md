# Swarnam4U cloud Shorts pipeline

This branch adds a first cloud-generated bilingual video stage. It does not change the live website or its existing rate updater.

## What this branch does
- Checks the current AKGSMA board date in Asia/Kolkata.
- Checks that the saved 22K/916, 18K/750 and silver 999 values and their record dates match the live board.
- Generates one English and one Malayalam vertical video per run.
- Adds the publication date, source label, rates, and the exact website text `swarnam4u.onrender.com`.
- Generates neural voice tracks and renders 1080×1920 H.264/AAC MP4s.
- Checks generated dimensions and file size, then saves MP4, PNG, MP3, and a manifest as a workflow artifact for review.

## Target slots
The three cloud starts are scheduled for 09:45, 12:45 and 16:45 India time, aiming to prepare a bilingual pair for 10:00, 13:00 and 17:00. GitHub Actions can be delayed; no exact-minute guarantee is possible.

If all three runs succeed, that is six generated clips per day: three English and three Malayalam.

## How to test after the pull request is merged
1. Open the repository's **Actions** tab.
2. Run **Swarnam4U Shorts Preflight** first.
3. Then run **Build Swarnam4U Shorts**, select a slot, and inspect its artifact.
4. Listen to both audio tracks, check Malayalam shaping/pronunciation and the full-screen text, and view the MP4 on a phone before using the videos.

The scheduled build only runs once the workflow is present on the default branch. It is intentionally not enabled for YouTube uploading yet.

## Current limitations
- No YouTube upload or scheduled publication is configured. Files are currently uploaded only as GitHub workflow artifacts for review.
- The current board date and saved published-rate values must pass preflight. When AKGSMA has not published today's board rates, generation stops; no stale rates are published.
- The video displays only the board's published 22K/916, 18K/750 and silver 999 values. It does not show 925 silver because AKGSMA has been showing it as unavailable.
- Calculated 24K/14K prices, platinum fallbacks, and estimated values are deliberately excluded from these Shorts.
- Neural TTS availability, Malayalam pronunciation, final aesthetics and end-to-end video playback still need review from a successful live workflow artifact.
- YouTube OAuth/client credentials, secure GitHub Secrets, duplicate-upload prevention, and YouTube scheduling are future tasks.

The publish gate stays disabled until those checks are completed. Do not edit snapshot timestamps or copy old prices forward to bypass preflight.
