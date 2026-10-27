import hmac
import os
import secrets
from datetime import timedelta
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SESSION_SECRET", "")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "rishalaliii")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "swarnam4u")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
WORKFLOW_FILE = os.environ.get("GITHUB_WORKFLOW_FILE", "build-shorts.yml")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
GITHUB_API = "https://api.github.com"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


def config_ready():
    return bool(app.secret_key and os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD") and GITHUB_TOKEN)


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped


def csrf_ok():
    token = request.headers.get("X-CSRF-Token", "")
    return bool(token and session.get("csrf") and hmac.compare_digest(token, session["csrf"]))


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; img-src 'self' data: https://i.ytimg.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.get("/")
def home():
    return redirect(url_for("dashboard") if session.get("admin") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        expected_user = os.environ.get("ADMIN_USERNAME", "")
        expected_password = os.environ.get("ADMIN_PASSWORD", "")
        user = request.form.get("username", "")
        password = request.form.get("password", "")
        if expected_user and expected_password and hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected_password):
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_urlsafe(32)
            session.permanent = True
            return redirect(url_for("dashboard"))
        error = "Username or password is incorrect."
    return render_template("login.html", error=error, setup=bool(app.secret_key and os.environ.get("ADMIN_USERNAME") and os.environ.get("ADMIN_PASSWORD")))


@app.post("/logout")
@admin_required
def logout():
    if not csrf_ok():
        return "Invalid request token", 400
    session.clear()
    return redirect(url_for("login"))


@app.get("/dashboard")
@admin_required
def dashboard():
    return render_template("dashboard.html", csrf=session.get("csrf", ""))


@app.get("/api/overview")
@admin_required
def overview():
    result = {"configured": config_ready(), "github_connected": bool(GITHUB_TOKEN), "youtube_configured": bool(YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID), "server_time": datetime.now(timezone.utc).isoformat()}
    try:
        response = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}", headers=github_headers(), timeout=12)
        response.raise_for_status()
        workflow = response.json()
        result["workflow"] = {"name": workflow.get("name", "Shorts workflow"), "state": workflow.get("state", "unknown"), "html_url": workflow.get("html_url", f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions")}
    except requests.RequestException:
        result["workflow"] = {"name": "Shorts workflow", "state": "unavailable", "html_url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions"}
    try:
        response = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs", headers=github_headers(), params={"per_page": 10}, timeout=12)
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        result["latest_runs"] = [{
            "id": run.get("id"), "name": run.get("display_title") or run.get("name"),
            "status": run.get("status"), "conclusion": run.get("conclusion"),
            "event": run.get("event"), "created_at": run.get("created_at"),
            "html_url": run.get("html_url"), "run_number": run.get("run_number"),
        } for run in runs]
        result["run_count"] = len(runs)
        result["latest_conclusion"] = runs[0].get("conclusion") if runs else None
    except requests.RequestException:
        result["latest_runs"] = []
        result["run_error"] = "Could not read GitHub Actions runs. Check the token's Actions: read permission."
    return jsonify(result)


@app.get("/api/runs")
@admin_required
def runs():
    try:
        r = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/runs", headers=github_headers(), params={"per_page": 30}, timeout=15)
        r.raise_for_status()
        items = r.json().get("workflow_runs", [])
        return jsonify([{"id": x.get("id"), "title": x.get("display_title") or x.get("name"), "status": x.get("status"), "conclusion": x.get("conclusion"), "event": x.get("event"), "created_at": x.get("created_at"), "updated_at": x.get("updated_at"), "url": x.get("html_url")} for x in items])
    except requests.RequestException as exc:
        return jsonify({"error": "GitHub could not return workflow runs. Verify GITHUB_TOKEN permissions.", "detail": str(exc)}), 502


@app.get("/api/runs/<int:run_id>/artifacts")
@admin_required
def artifacts(run_id):
    try:
        r = requests.get(f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/artifacts", headers=github_headers(), timeout=15)
        r.raise_for_status()
        items = r.json().get("artifacts", [])
        return jsonify([{"id": x.get("id"), "name": x.get("name"), "size_in_bytes": x.get("size_in_bytes"), "expired": x.get("expired"), "created_at": x.get("created_at"), "download_url": x.get("archive_download_url")} for x in items])
    except requests.RequestException as exc:
        return jsonify({"error": "Unable to load artifacts. Check Actions: read permission.", "detail": str(exc)}), 502


@app.post("/api/dispatch")
@admin_required
def dispatch():
    if not csrf_ok():
        return jsonify({"error": "Invalid request token. Refresh the page and try again."}), 400
    if not GITHUB_TOKEN:
        return jsonify({"error": "GITHUB_TOKEN is not configured on the admin service."}), 503
    body = request.get_json(silent=True) or {}
    slot = body.get("slot")
    mode = body.get("mode")
    if slot not in {"morning", "midday", "evening"}:
        return jsonify({"error": "Choose morning, midday, or evening."}), 400
    if mode not in {"build_only", "schedule_private", "public_now"}:
        return jsonify({"error": "Invalid publishing mode."}), 400
    if mode == "public_now" and body.get("confirm_public") is not True:
        return jsonify({"error": "Public upload requires explicit confirmation."}), 400
    endpoint = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": GITHUB_BRANCH, "inputs": {"slot": slot, "publish_mode": mode}}
    try:
        r = requests.post(endpoint, headers=github_headers(), json=payload, timeout=20)
        if r.status_code not in (200, 201, 204):
            return jsonify({"error": f"GitHub rejected the workflow request ({r.status_code}).", "detail": r.text[:1200]}), 502
        return jsonify({"ok": True, "message": "Workflow dispatch accepted. Refresh run history in a few seconds.", "actions_url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}"})
    except requests.RequestException as exc:
        return jsonify({"error": "Could not reach GitHub.", "detail": str(exc)}), 502


@app.get("/api/youtube")
@admin_required
def youtube():
    if not YOUTUBE_API_KEY or not YOUTUBE_CHANNEL_ID:
        return jsonify({"configured": False, "message": "Add YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID in Render to show channel and public video statistics."})
    try:
        channel_response = requests.get(f"{YOUTUBE_API}/channels", params={"part": "snippet,statistics,contentDetails", "id": YOUTUBE_CHANNEL_ID, "key": YOUTUBE_API_KEY}, timeout=15)
        channel_response.raise_for_status()
        channels = channel_response.json().get("items", [])
        if not channels:
            return jsonify({"configured": True, "error": "Channel not found. Verify YOUTUBE_CHANNEL_ID."}), 404
        channel = channels[0]
        playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        playlist_response = requests.get(f"{YOUTUBE_API}/playlistItems", params={"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 15, "key": YOUTUBE_API_KEY}, timeout=15)
        playlist_response.raise_for_status()
        playlist_items = playlist_response.json().get("items", [])
        ids = ",".join(item["contentDetails"]["videoId"] for item in playlist_items if item.get("contentDetails", {}).get("videoId"))
        videos = []
        if ids:
            vr = requests.get(f"{YOUTUBE_API}/videos", params={"part": "snippet,statistics,status", "id": ids, "key": YOUTUBE_API_KEY}, timeout=15)
            vr.raise_for_status()
            videos = [{"id": v["id"], "title": v.get("snippet", {}).get("title", "Untitled"), "published_at": v.get("snippet", {}).get("publishedAt"), "thumbnail": v.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url"), "views": int(v.get("statistics", {}).get("viewCount", 0)), "likes": int(v.get("statistics", {}).get("likeCount", 0)), "comments": int(v.get("statistics", {}).get("commentCount", 0)), "privacy": v.get("status", {}).get("privacyStatus", "unknown"), "url": f"https://www.youtube.com/watch?v={v['id']}"} for v in videos]
        return jsonify({"configured": True, "channel": {"title": channel["snippet"]["title"], "thumbnail": channel["snippet"].get("thumbnails", {}).get("default", {}).get("url"), "subscribers": int(channel.get("statistics", {}).get("subscriberCount", 0)), "views": int(channel.get("statistics", {}).get("viewCount", 0)), "video_count": int(channel.get("statistics", {}).get("videoCount", 0)), "url": f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}"}, "videos": videos})
    except requests.RequestException as exc:
        return jsonify({"configured": True, "error": "YouTube API request failed. Check API key, quota, and channel ID.", "detail": str(exc)}), 502


@app.get("/health")
def health():
    return jsonify({"ok": True})


if not app.secret_key:
    app.logger.warning("ADMIN_SESSION_SECRET is missing; set it in the hosting provider environment.")
