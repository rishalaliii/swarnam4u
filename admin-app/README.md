# Swarnam4U Neon Admin

A separate private admin service. It does not replace the public website and does not change the existing scheduled rate workflow.

## Included
- Password-protected admin session, security headers, login rate limiting, CSRF-origin checks for state-changing requests.
- Current public rate snapshot read from the repository.
- GitHub Actions run history and manually dispatchable workflows, restricted by `GITHUB_ALLOWED_WORKFLOWS`.
- YouTube OAuth connect and direct video upload (title, description, visibility, category, language).
- GitHub Actions secret toggles for `YOUTUBE_AUTO_PUBLISH` and `YOUTUBE_UPLOAD_KILL_SWITCH` using GitHub's public-key encryption endpoint.
- Emergency stop writes the kill-switch secret first and disables auto-publish; this affects future workflow runs, not jobs already in progress.
- UI explicitly separates live connections from unconfigured services.

## Required deployment configuration
Set all values from `.env.example` in the private admin host's environment. Do not put credentials in GitHub files, screenshots, chat, or client-side code.

Google Cloud:
1. Enable YouTube Data API v3.
2. Create OAuth client type **Web application**.
3. Set the authorized redirect URI to `https://YOUR-ADMIN-HOST/auth/youtube/callback`.
4. Configure OAuth consent screen and add the intended channel owner as a test user while the app is in testing.
5. Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and a strong `TOKEN_ENCRYPTION_KEY` (32 random bytes encoded as hex) to the host's private environment.
6. The OAuth flow requests offline access and stores the refresh token encrypted at rest. Configure `TOKEN_STORE_PATH` on persistent storage if the host has ephemeral filesystems. If a refresh token is returned only once, keep a secure backup.

GitHub:
1. Create a dedicated token with minimum repository access for `rishalaliii/swarnam4u`: Actions read/write, Contents read, and Actions secrets read/write only if you want the kill-switch controls.
2. Set `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`.
3. Set `GITHUB_ALLOWED_WORKFLOWS` to comma-separated workflow filenames you intentionally permit to dispatch. Keep this empty until you have reviewed the workflows; an empty list disables manual dispatch.
4. The app never reads secret values back. GitHub secrets are write-only.

## Deployment
Deploy this folder as a **separate Render web service** using `admin-app/render.yaml` or configure root directory `admin-app`, build `npm install`, start `npm start`. Add environment variables in the host dashboard, never in this repository. Keep the admin URL private and use a unique password. Render service creation and environment configuration must be completed in the hosting dashboard.

## Important limitations
- GitHub workflow dispatch is only available for workflows explicitly listed in `GITHUB_ALLOWED_WORKFLOWS`. The current rates workflow is not automatically treated as a YouTube workflow.
- GitHub's Actions secrets API does not expose current values; the UI reports write results, not a read-back.
- A kill switch prevents future automation runs only if the existing YouTube workflow checks `YOUTUBE_UPLOAD_KILL_SWITCH` before upload. Inspect that workflow before enabling automation.
- Unreviewed OAuth apps can be restricted to private uploads by YouTube/Google policy. Test with private visibility first.
- This admin app does not merge or deploy changes to the public site.


## Admin automation controls (feature branch)

This admin-only update does not edit the public website or any workflow YAML files.

- Add `.github/workflows/build-shorts.yml` to `GITHUB_ALLOWED_WORKFLOWS` in Render to enable manual Shorts dispatch with a selected slot and `publish_mode`. `build_only` is the safe default; `public_now` requires confirmation. A dispatch acknowledgement is not proof of a successful upload.
- The Shorts workflow reads `YOUTUBE_UPLOAD_KILL_SWITCH` and `YOUTUBE_AUTO_PUBLISH` from GitHub Actions repository **variables**. The admin now reads/writes variables instead of same-named secrets. The GitHub token needs Actions variables read/write permissions.
- Set `CRONJOB_API_KEY` and numeric `CRONJOB_JOB_ID` in Render environment variables for cron-job.org status/history and enable/pause controls. The API key is never sent to the browser or stored in the repository.
- Pausing the external timer does not disable the independent GitHub Actions schedules for Shorts/rate updates. The panel controls the configured job and does not create or rewrite its schedule.
