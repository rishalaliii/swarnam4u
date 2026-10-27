const $ = (id) => document.getElementById(id);
const csrf = document.body.dataset.csrf || "";
const fmt = (n) => new Intl.NumberFormat("en-IN", { notation: n > 999999 ? "compact" : "standard", maximumFractionDigits: 1 }).format(Number(n || 0));
const dateFmt = (value) => value ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: true }) : "—";
async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { credentials: "same-origin", ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { location.href = "/login"; throw new Error("Your session expired. Sign in again."); }
  if (!response.ok) throw new Error(data.error || "Request failed.");
  return data;
}
function toast(message, error = false) {
  const el = $("toast"); el.textContent = message; el.className = "toast show" + (error ? " error" : "");
  window.setTimeout(() => el.classList.remove("show"), 7000);
}
function stateLabel(run) {
  if (run.status !== "completed") return run.status || "unknown";
  return run.conclusion || "completed";
}
function stateClass(run) {
  const s = stateLabel(run);
  return ["success"].includes(s) ? "success" : ["failure", "cancelled", "timed_out", "action_required"].includes(s) ? "failure" : "";
}
async function loadOverview() {
  try {
    const d = await api("/api/overview");
    $("automation-state").textContent = d.workflow?.state === "active" ? "Active" : (d.workflow?.state || "Unknown");
    $("latest-build").textContent = d.latest_runs?.length ? stateLabel(d.latest_runs[0]) : "No runs yet";
    $("latest-build-foot").textContent = d.latest_runs?.length ? dateFmt(d.latest_runs[0].created_at) : "Run the first build";
    $("automation-state").style.color = d.workflow?.state === "active" ? "var(--green)" : "var(--gold2)";
    renderRuns(d.latest_runs || []);
  } catch (e) { $("automation-state").textContent = "Unavailable"; $("latest-build").textContent = "Unknown"; }
}
async function loadYoutube() {
  try {
    const d = await api("/api/youtube");
    if (!d.configured) { $("youtube-notice").textContent = d.message; $("video-rows").innerHTML = '<tr><td colspan="6" class="empty-cell">Connect YouTube API to view your video statistics.</td></tr>'; return; }
    if (d.error) throw new Error(d.error);
    $("channel-views").textContent = fmt(d.channel.views);
    $("video-count").textContent = fmt(d.channel.video_count);
    $("channel-link").href = d.channel.url;
    $("youtube-notice").textContent = d.channel.title + " · " + fmt(d.channel.subscribers) + " subscribers · Showing up to 15 recent videos";
    $("video-rows").innerHTML = d.videos.length ? d.videos.map(v => '<tr><td><a class="video-title-cell" href="' + esc(v.url) + '" target="_blank" rel="noreferrer"><img src="' + esc(v.thumbnail || "") + '" alt=""><span>' + esc(v.title) + '</span></a></td><td><span class="privacy ' + esc(v.privacy) + '">' + esc(v.privacy) + '</span></td><td>' + fmt(v.views) + '</td><td>' + fmt(v.likes) + '</td><td>' + dateFmt(v.published_at) + '</td><td><a class="run-link" href="' + esc(v.url) + '" target="_blank" rel="noreferrer">↗</a></td></tr>').join("") : '<tr><td colspan="6" class="empty-cell">No videos found for this channel.</td></tr>';
  } catch (e) { $("youtube-notice").textContent = e.message; $("video-rows").innerHTML = '<tr><td colspan="6" class="empty-cell">Video stats unavailable. Check the YouTube API configuration.</td></tr>'; }
}
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function renderRuns(runs) {
  const el = $("runs-list");
  if (!runs.length) { el.innerHTML = '<div class="empty-cell">No workflow runs found yet.</div>'; return; }
  el.innerHTML = runs.slice(0, 8).map(r => {
    const status = stateLabel(r), cls = stateClass(r);
    const symbol = cls === "success" ? "✓" : cls === "failure" ? "!" : "◷";
    return '<div class="run-row"><div class="run-state ' + cls + '">' + symbol + '</div><div class="run-main"><b>' + esc(r.name || r.title || "Shorts workflow") + '</b><small>' + dateFmt(r.created_at) + ' · ' + esc(r.event || "workflow") + '</small></div><span class="run-badge ' + cls + '">' + esc(status) + '</span><a class="run-link" href="' + esc(r.html_url || r.url || "#") + '" target="_blank" rel="noreferrer" aria-label="Open run">↗</a></div>';
  }).join("");
}
$("mode").addEventListener("change", () => {
  const mode = $("mode").value;
  $("confirm-row").hidden = mode !== "public_now";
  const copy = {
    build_only: ["Safe mode selected.", "Generate the videos and download the artifact. Nothing will be uploaded automatically."],
    schedule_private: ["Private scheduling selected.", "The workflow will create private uploads and apply YouTube scheduling if configured."],
    public_now: ["Public publishing selected.", "This can publish both videos publicly. Confirm below before starting."]
  }[mode];
  $("mode-note").innerHTML = "<span>ⓘ</span><p><b>" + copy[0] + "</b> " + copy[1] + "</p>";
});
$("dispatch-btn").addEventListener("click", async () => {
  const mode = $("mode").value;
  if (mode === "public_now" && !$("confirm-public").checked) { toast("Tick the confirmation box before public publishing.", true); return; }
  if (mode === "public_now" && !window.confirm("Publish both English and Malayalam videos publicly to YouTube now?")) return;
  const btn = $("dispatch-btn"); btn.disabled = true; btn.textContent = "Starting workflow…";
  try {
    const d = await api("/api/dispatch", { method: "POST", body: JSON.stringify({ slot: $("slot").value, mode, confirm_public: $("confirm-public").checked }) });
    toast(d.message); $("confirm-public").checked = false;
    window.setTimeout(() => { loadOverview(); loadRuns(); }, 4000);
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.innerHTML = '<span>▶</span> Start workflow <span class="btn-arrow">↗</span>'; }
});
async function loadRuns() {
  try { renderRuns(await api("/api/runs")); } catch (e) { $("runs-list").innerHTML = '<div class="empty-cell">' + esc(e.message) + '</div>'; }
}
$("refresh").addEventListener("click", refreshAll);
$("runs-refresh").addEventListener("click", loadRuns);
async function refreshAll() { $("refresh").textContent = "…"; await Promise.all([loadOverview(), loadYoutube(), loadRuns()]); $("refresh").textContent = "↻"; }
$("mobile-menu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
document.querySelectorAll(".nav-item[data-section]").forEach(a => a.addEventListener("click", () => {
  document.querySelectorAll(".nav-item[data-section]").forEach(n => n.classList.remove("active")); a.classList.add("active");
  $("current-crumb").textContent = a.textContent.trim().replace(/^\S+\s*/, "");
  $("page-title").textContent = a.dataset.section === "overview" ? "Creator control room" : a.textContent.trim();
  $("sidebar").classList.remove("open");
}));
document.querySelector(".sidebar-bottom form")?.addEventListener("submit", e => {
  e.preventDefault();
  fetch("/logout", { method: "POST", headers: { "X-CSRF-Token": csrf }, credentials: "same-origin" }).then(() => location.href = "/login");
});
$("today-date").textContent = new Date().toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short", year: "numeric" });
refreshAll();
