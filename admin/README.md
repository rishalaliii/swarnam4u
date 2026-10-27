# Swarnam4U Creator Control Room

A separate Flask service for the Swarnam4U admin dashboard. Keep this service private through login; do not place tokens or passwords in frontend code.

## Deploy as a separate Render Web Service

1. In Render, create a **New Web Service** connected to `rishalaliii/swarnam4u`.
2. Set **Root Directory** to `admin`.
3. Runtime: Python. Build command: `pip install -r requirements.txt`.
4. Start command: `gunicorn --workers 2 --threads 4 --timeout 45 app:app`.
5. Add the environment variables below. Generate a long random `ADMIN_SESSION_SECRET` (at least 32 random characters). Choose a unique admin password; do not commit it to GitHub.
6. Set the service to deploy from `main` only after reviewing and merging the feature branch / PR.

## Required environment variables

- `ADMIN_USERNAME`: your chosen unique admin username.
- `ADMIN_PASSWORD`: a long, unique password used only for this dashboard.
- `ADMIN_SESSION_SECRET`: long random session signing secret.
- `GITHUB_TOKEN`: fine-grained GitHub token limited to this repository, with **Actions: Read and write**. Read access to workflow runs/artifacts and write access to dispatch workflows are needed. Never add it to website JavaScript.
- `GITHUB_OWNER`: `rishalaliii`
- `GITHUB_REPO`: `swarnam4u`
- `GITHUB_BRANCH`: `main`
- `GITHUB_WORKFLOW_FILE`: `build-shorts.yml`

Optional public YouTube metrics:
- `YOUTUBE_API_KEY`: YouTube Data API v3 key from a Google Cloud project with YouTube Data API v3 enabled.
- `YOUTUBE_CHANNEL_ID`: the channel's actual ID (starts with UC). This is not the @handle.

## Current scope and limitations

- Secure session-based admin login with HTTP-only, Secure, SameSite=Lax cookie, CSRF token checks, security headers, and server-only secrets.
- Start a workflow for morning/midday/evening in build-only, private-scheduling, or public-now mode. Public-now requires a checkbox and browser confirmation.
- Read recent GitHub workflow runs and their status; read artifact metadata; links take you to GitHub to download artifacts.
- Show public channel views, subscriber count, video count, and up to 15 recent videos' views/likes/comments/privacy status. These are Data API values and may be delayed.
- The schedule display mirrors the existing GitHub cron: 10:10, 12:30 and 16:30 IST starts. Editing cron from the UI is not implemented in this initial version; change `.github/workflows/build-shorts.yml` to modify it.
- Private scheduling/public uploads still depend on the repository's existing YouTube OAuth secrets and workflow guard variables. The admin dashboard cannot reveal or modify repository secrets. Manual uploads of arbitrary MP4 files and YouTube Analytics metrics (watch time, retention, reach) are not implemented here.
- This is a first admin-control implementation, not an assertion that a workflow has run or a video has been uploaded. Verify each run and upload in the dashboard / YouTube Studio.

## Safety

Do not use a personal classic PAT with broad account access if a fine-grained token can be used. Do not reuse your website, email, or banking password. Rotate any credential accidentally exposed in logs or commits.
