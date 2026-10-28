"use strict";
const express = require("express");
const session = require("express-session");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const multer = require("multer");
const { google } = require("googleapis");
const sodium = require("libsodium-wrappers");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const app = express();
const PORT = Number(process.env.PORT || 10000);
const ROOT = __dirname;
const PUBLIC = path.join(ROOT, "public");
const DATA = path.join(ROOT, "data");
const TOKEN_FILE = path.resolve(process.env.TOKEN_STORE_PATH || path.join(DATA, "youtube-token.enc"));
const UPLOAD_TMP = path.join(DATA, "uploads");
fs.mkdirSync(UPLOAD_TMP, { recursive: true });
fs.mkdirSync(path.dirname(TOKEN_FILE), { recursive: true });

const required = ["ADMIN_USERNAME", "ADMIN_PASSWORD", "SESSION_SECRET"];
const missing = required.filter(k => !process.env[k]);
if (missing.length) console.warn("Missing required environment variables:", missing.join(", "));

app.disable("x-powered-by");
app.set("trust proxy", 1);
app.use(helmet({ contentSecurityPolicy: {
  directives: {
    defaultSrc: ["'self'"], scriptSrc: ["'self'"], styleSrc: ["'self'", "'unsafe-inline'"],
    imgSrc: ["'self'", "data:", "blob:"], connectSrc: ["'self'"], mediaSrc: ["'self'", "blob:"],
    objectSrc: ["'none'"], frameAncestors: ["'none'"], upgradeInsecureRequests: []
  }
}}));
app.use(express.json({ limit: "100kb" }));
app.use(session({
  name: "swarnam_admin",
  secret: process.env.SESSION_SECRET || "unsafe-development-secret",
  resave: false, saveUninitialized: false,
  cookie: { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", maxAge: 8 * 60 * 60 * 1000 }
}));
const loginLimiter = rateLimit({ windowMs: 15 * 60 * 1000, limit: 8, standardHeaders: true, legacyHeaders: false });
const upload = multer({
  dest: UPLOAD_TMP, limits: { fileSize: 512 * 1024 * 1024, files: 1 },
  fileFilter: (_req, file, cb) => {
    const allowed = new Set(["video/mp4", "video/quicktime", "video/webm", "video/x-msvideo", "video/mpeg"]);
    cb(allowed.has(file.mimetype) ? null : new Error("Unsupported video format. Use MP4, MOV, WebM, AVI, or MPEG."), allowed.has(file.mimetype));
  }
});

function appendLocalLog(fileName, event) {
  const file = path.join(DATA, fileName);
  let rows = [];
  try { rows = JSON.parse(fs.readFileSync(file, "utf8")); if (!Array.isArray(rows)) rows = []; } catch {}
  rows.unshift({ at: new Date().toISOString(), ...event });
  fs.writeFileSync(file, JSON.stringify(rows.slice(0, 500), null, 2), { mode: 0o600 });
}
function timingSafeString(a, b) {
  const aa = Buffer.from(String(a || ""));
  const bb = Buffer.from(String(b || ""));
  return aa.length === bb.length && crypto.timingSafeEqual(aa, bb);
}
function requireAuth(req, res, next) {
  if (req.session && req.session.authenticated === true) return next();
  return res.status(401).json({ error: "Sign in to continue." });
}
function sameOrigin(req, res, next) {
  const origin = req.get("origin");
  const base = process.env.APP_BASE_URL;
  if (origin && base && new URL(origin).origin !== new URL(base).origin) return res.status(403).json({ error: "Origin check failed." });
  next();
}
function githubConfig() {
  if (!process.env.GITHUB_TOKEN || !process.env.GITHUB_OWNER || !process.env.GITHUB_REPO)
    throw new Error("GitHub is not configured. Add GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO in the host environment.");
  return { owner: process.env.GITHUB_OWNER, repo: process.env.GITHUB_REPO, token: process.env.GITHUB_TOKEN };
}
async function gh(url, options = {}) {
  const cfg = githubConfig();
  const response = await fetch("https://api.github.com" + url, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: "Bearer " + cfg.token,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {})
    }
  });
  const body = await response.text();
  let parsed; try { parsed = body ? JSON.parse(body) : {}; } catch { parsed = { message: body.slice(0, 300) }; }
  if (!response.ok) throw new Error("GitHub API " + response.status + ": " + (parsed.message || response.statusText));
  return parsed;
}
function oauthClient() {
  if (!process.env.GOOGLE_CLIENT_ID || !process.env.GOOGLE_CLIENT_SECRET || !process.env.GOOGLE_REDIRECT_URI)
    throw new Error("YouTube OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI.");
  return new google.auth.OAuth2(process.env.GOOGLE_CLIENT_ID, process.env.GOOGLE_CLIENT_SECRET, process.env.GOOGLE_REDIRECT_URI);
}
function encryptionKey() {
  const raw = process.env.TOKEN_ENCRYPTION_KEY || "";
  if (!/^[0-9a-fA-F]{64}$/.test(raw)) throw new Error("TOKEN_ENCRYPTION_KEY must be 64 hex characters (32 random bytes).");
  return Buffer.from(raw, "hex");
}
function saveTokens(tokens) {
  if (!tokens.refresh_token && fs.existsSync(TOKEN_FILE)) {
    try { tokens.refresh_token = readTokens().refresh_token; } catch {}
  }
  const key = encryptionKey();
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const enc = Buffer.concat([cipher.update(JSON.stringify(tokens), "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  const tmp = TOKEN_FILE + ".tmp";
  fs.writeFileSync(tmp, Buffer.concat([iv, tag, enc]), { mode: 0o600 });
  fs.renameSync(tmp, TOKEN_FILE);
}
function readTokens() {
  if (!fs.existsSync(TOKEN_FILE)) return {};
  const buf = fs.readFileSync(TOKEN_FILE);
  if (buf.length < 29) throw new Error("Stored token file is invalid.");
  const decipher = crypto.createDecipheriv("aes-256-gcm", encryptionKey(), buf.subarray(0, 12));
  decipher.setAuthTag(buf.subarray(12, 28));
  const clear = Buffer.concat([decipher.update(buf.subarray(28)), decipher.final()]);
  return JSON.parse(clear.toString("utf8"));
}
function getYoutubeClient() {
  const auth = oauthClient();
  let tokens = {};
  try { tokens = readTokens(); } catch (e) { console.error("Token store read failed:", e.message); }
  if (!tokens.refresh_token && process.env.YOUTUBE_REFRESH_TOKEN) tokens.refresh_token = process.env.YOUTUBE_REFRESH_TOKEN;
  if (!tokens.refresh_token) throw new Error("YouTube is not connected. Use Connect YouTube first.");
  auth.setCredentials(tokens);
  auth.on("tokens", updated => {
    try { saveTokens({ ...tokens, ...updated, refresh_token: updated.refresh_token || tokens.refresh_token }); }
    catch (e) { console.error("Could not persist refreshed OAuth token:", e.message); }
  });
  return { auth, youtube: google.youtube({ version: "v3", auth }) };
}

app.get("/health", (_req, res) => res.json({ ok: true, service: "swarnam4u-admin" }));
app.get("/api/session", (req, res) => res.json({ authenticated: req.session?.authenticated === true, username: req.session?.username || null }));
app.post("/api/login", loginLimiter, sameOrigin, (req, res) => {
  if (!timingSafeString(req.body?.username, process.env.ADMIN_USERNAME) ||
      !timingSafeString(req.body?.password, process.env.ADMIN_PASSWORD)) {
    return res.status(401).json({ error: "Invalid username or password." });
  }
  req.session.regenerate(err => {
    if (err) return res.status(500).json({ error: "Could not create secure session." });
    req.session.authenticated = true;
    req.session.username = process.env.ADMIN_USERNAME;
    try { appendLocalLog("audit.json", { actor: req.session.username, action: "login_success" }); } catch (e) { console.error("Audit log write failed:", e.message); }
    req.session.save(e => e ? res.status(500).json({ error: "Could not save session." }) : res.json({ ok: true }));
  });
});
app.post("/api/logout", sameOrigin, (req, res) => req.session.destroy(() => {
  res.clearCookie("swarnam_admin", { httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production" });
  res.json({ ok: true });
}));

app.get("/api/audit", requireAuth, (_req, res) => {
  try { const rows = JSON.parse(fs.readFileSync(path.join(DATA, "audit.json"), "utf8")); res.json({ events: Array.isArray(rows) ? rows.slice(0, 100) : [] }); }
  catch { res.json({ events: [] }); }
});
app.get("/api/upload-history", requireAuth, (_req, res) => {
  try { const rows = JSON.parse(fs.readFileSync(path.join(DATA, "upload-history.json"), "utf8")); res.json({ uploads: Array.isArray(rows) ? rows.slice(0, 100) : [] }); }
  catch { res.json({ uploads: [] }); }
});

app.get("/api/dashboard", requireAuth, async (_req, res) => {
  const status = { github: false, youtube: false, rates: null, workflows: [], recentRuns: [], warnings: [] };
  try {
    const cfg = githubConfig();
    const repo = await gh("/repos/" + cfg.owner + "/" + cfg.repo);
    status.github = true;
    status.repository = { fullName: repo.full_name, defaultBranch: repo.default_branch, visibility: repo.private ? "private" : "public", url: repo.html_url };
    const file = await gh("/repos/" + cfg.owner + "/" + cfg.repo + "/contents/data/rates.json");
    status.rates = JSON.parse(Buffer.from(file.content.replace(/\n/g, ""), "base64").toString("utf8"));
    const [workflows, runs] = await Promise.all([
      gh("/repos/" + cfg.owner + "/" + cfg.repo + "/actions/workflows?per_page=100"),
      gh("/repos/" + cfg.owner + "/" + cfg.repo + "/actions/runs?per_page=8")
    ]);
    status.workflows = (workflows.workflows || []).map(w => ({ id: w.id, name: w.name, path: w.path, state: w.state, url: w.html_url }));
    status.recentRuns = (runs.workflow_runs || []).map(r => ({ id: r.id, name: r.name, status: r.status, conclusion: r.conclusion, createdAt: r.created_at, url: r.html_url }));
  } catch (e) { status.warnings.push("GitHub: " + e.message); }
  try {
    const { youtube } = getYoutubeClient();
    const ch = await youtube.channels.list({ part: ["snippet"], mine: true, maxResults: 1 });
    const c = ch.data.items?.[0];
    status.youtube = !!c;
    if (c) status.channel = { title: c.snippet?.title, id: c.id };
  } catch (e) { status.warnings.push("YouTube: " + e.message); }
  status.autoPublishConfigured = !!process.env.GITHUB_TOKEN;
  try{const[kill,automatic]=await Promise.all([getGithubVariable("YOUTUBE_UPLOAD_KILL_SWITCH"),getGithubVariable("YOUTUBE_AUTO_PUBLISH")]);status.publishing={killSwitch:kill==="true",autoPublish:automatic==="true",configured:kill!==null||automatic!==null};}catch(e){status.publishing={configured:false,warning:e.message};}
  try{const jobs=cronConfigs();status.cronjob={configured:true,jobs:await Promise.all(jobs.map(async item=>{const r=await cronRequest("/jobs/"+encodeURIComponent(item.jobId));return {...safeCronJob(r.jobDetails||r.job||r),slot:item.slot};}))};}catch(e){status.cronjob={configured:false,warning:e.message};}
  res.json(status);
});


function cronConfig(){const apiKey=process.env.CRONJOB_API_KEY||"";if(!apiKey)throw new Error("Cron-job.org is not configured. Set CRONJOB_API_KEY in Render environment.");return{apiKey};}
function cronConfigs(){const raw=String(process.env.CRONJOB_JOB_IDS||"").trim();let jobs=[];if(raw){jobs=raw.split(",").map(part=>{const m=part.trim().match(/^([a-zA-Z_-]+):(\\d+)$/);if(!m)throw new Error("CRONJOB_JOB_IDS must use slot:id pairs, e.g. morning:123,midday:456,evening:789.");return{slot:m[1].toLowerCase(),jobId:m[2]};});}else{const id=String(process.env.CRONJOB_JOB_ID||"").trim();if(id){if(!/^\\d+$/.test(id))throw new Error("CRONJOB_JOB_ID must be numeric.");jobs=[{slot:"configured",jobId:id}];}}if(!jobs.length)throw new Error("Set CRONJOB_JOB_IDS in Render (morning:8742599,midday:8742601,evening:8742620).");if(new Set(jobs.map(j=>j.jobId)).size!==jobs.length)throw new Error("Cron job IDs must be unique.");return jobs;}
async function cronRequest(pathname,options={}){const{apiKey}=cronConfig();const r=await fetch("https://api.cron-job.org"+pathname,{...options,headers:{Authorization:"Bearer "+apiKey,Accept:"application/json",...(options.body?{"Content-Type":"application/json"}:{}),...(options.headers||{})}});const raw=await r.text();let data={};try{data=raw?JSON.parse(raw):{};}catch{data={message:raw.slice(0,250)};}if(!r.ok)throw new Error("cron-job.org API "+r.status+": "+(data.message||data.error||r.statusText));return data;}
function safeCronJob(j){if(!j)return null;return{jobId:j.jobId,title:j.title,enabled:!!j.enabled,url:j.url,lastStatus:j.lastStatus,lastDuration:j.lastDuration,lastExecution:j.lastExecution,nextExecution:j.nextExecution,requestMethod:j.requestMethod,schedule:j.schedule,requestTimeout:j.requestTimeout};}
async function setGithubVariable(name,value){const c=githubConfig(),url="/repos/"+c.owner+"/"+c.repo+"/actions/variables/"+encodeURIComponent(name);try{await gh(url,{method:"PATCH",body:JSON.stringify({name,value})});}catch(e){if(!String(e.message).includes(" 404:"))throw e;await gh("/repos/"+c.owner+"/"+c.repo+"/actions/variables",{method:"POST",body:JSON.stringify({name,value})});}}
async function getGithubVariable(name){const c=githubConfig();try{return(await gh("/repos/"+c.owner+"/"+c.repo+"/actions/variables/"+encodeURIComponent(name))).value;}catch(e){if(String(e.message).includes(" 404:"))return null;throw e;}}
async function setPublishingState(stopped,actor){await setGithubVariable("YOUTUBE_UPLOAD_KILL_SWITCH",stopped?"true":"false");appendLocalLog("audit.json",{actor,action:stopped?"publishing_emergency_stop_requested":"publishing_resume_requested",target:"GitHub Actions repository variables"});await setGithubVariable("YOUTUBE_AUTO_PUBLISH",stopped?"false":"true");}
app.get("/api/github/publishing",requireAuth,async(_req,res)=>{try{const[killSwitch,autoPublish]=await Promise.all([getGithubVariable("YOUTUBE_UPLOAD_KILL_SWITCH"),getGithubVariable("YOUTUBE_AUTO_PUBLISH")]);res.json({ok:true,killSwitch:killSwitch==="true",autoPublish:autoPublish==="true",configured:killSwitch!==null||autoPublish!==null,note:"Reads the repository variables used by build-shorts.yml. Changes affect future workflow evaluations only."});}catch(e){res.status(502).json({error:e.message});}});
app.get("/api/cronjob",requireAuth,async(_req,res)=>{try{const jobs=cronConfigs();const results=await Promise.all(jobs.map(async item=>{const id=encodeURIComponent(item.jobId),r=await cronRequest("/jobs/"+id),job=r.jobDetails||r.job||r,h=await cronRequest("/jobs/"+id+"/history").catch(e=>({_historyError:e.message}));return{slot:item.slot,job:safeCronJob(job),history:(h.history||[]).slice(0,8).map(x=>({identifier:x.identifier,date:x.date,datePlanned:x.datePlanned,duration:x.duration,status:x.status,statusText:x.statusText,httpStatus:x.httpStatus})),historyWarning:h._historyError||null};}));res.json({configured:true,jobs:results});}catch(e){res.status(503).json({configured:false,error:e.message});}});
app.post("/api/cronjob/control",requireAuth,sameOrigin,async(req,res)=>{const enabled=req.body?.enabled,jobId=String(req.body?.jobId||"").trim();if(typeof enabled!=="boolean")return res.status(400).json({error:"enabled must be true or false."});try{const item=cronConfigs().find(x=>x.jobId===jobId);if(!item)return res.status(400).json({error:"Choose a configured cron job ID."});await cronRequest("/jobs/"+encodeURIComponent(jobId),{method:"PATCH",body:JSON.stringify({job:{enabled}})});appendLocalLog("audit.json",{actor:req.session.username,action:enabled?"cron_job_enabled":"cron_job_disabled",jobId,slot:item.slot});const r=await cronRequest("/jobs/"+encodeURIComponent(jobId));res.json({ok:true,job:safeCronJob(r.jobDetails||r.job||r),message:(item.slot==="configured"?"External cron job":item.slot+" cron job")+(enabled?" enabled.":" paused.")});}catch(e){res.status(502).json({error:e.message});}});
app.post("/api/cronjob/run-shorts",requireAuth,sameOrigin,async(req,res)=>{const slot=String(req.body?.slot||""),mode=String(req.body?.publishMode||"build_only");if(!["morning","midday","evening"].includes(slot))return res.status(400).json({error:"Choose morning, midday, or evening."});if(!["build_only","schedule_private","scheduled_release","public_now"].includes(mode))return res.status(400).json({error:"Invalid publishing mode."});if(mode==="public_now"&&!req.body?.confirmPublic)return res.status(400).json({error:"Explicit public-publish confirmation is required."});try{const c=githubConfig(),file=".github/workflows/build-shorts.yml",allow=(process.env.GITHUB_ALLOWED_WORKFLOWS||"").split(",").map(s=>s.trim()).filter(Boolean);if(!allow.includes(file))return res.status(403).json({error:"Add .github/workflows/build-shorts.yml to GITHUB_ALLOWED_WORKFLOWS in Render before dispatching Shorts."});const d=await gh("/repos/"+c.owner+"/"+c.repo+"/actions/workflows?per_page=100"),wf=(d.workflows||[]).find(w=>w.path===file&&w.state==="active");if(!wf)return res.status(404).json({error:"Active Shorts workflow not found."});await gh("/repos/"+c.owner+"/"+c.repo+"/actions/workflows/"+wf.id+"/dispatches",{method:"POST",body:JSON.stringify({ref:"main",inputs:{slot,publish_mode:mode}})});appendLocalLog("audit.json",{actor:req.session.username,action:"shorts_workflow_dispatch_requested",workflow:file,slot,publishMode:mode});res.json({ok:true,message:"Shorts workflow dispatch accepted by GitHub. Check Actions before assuming upload succeeded.",slot,publishMode:mode});}catch(e){res.status(502).json({error:e.message});}});

app.get("/api/github/workflows", requireAuth, async (_req, res) => {
  try {
    const c = githubConfig();
    const data = await gh("/repos/" + c.owner + "/" + c.repo + "/actions/workflows?per_page=100");
    res.json({ workflows: (data.workflows || []).map(w => ({ id: w.id, name: w.name, path: w.path, state: w.state, url: w.html_url })) });
  } catch (e) { res.status(502).json({ error: e.message }); }
});
app.post("/api/github/dispatch", requireAuth, sameOrigin, async (req, res) => {
  try {
    const c = githubConfig();
    const allowed = (process.env.GITHUB_ALLOWED_WORKFLOWS || "").split(",").map(s => s.trim()).filter(Boolean);
    const file = String(req.body?.workflow || "");
    if (!allowed.includes(file)) return res.status(403).json({ error: "This workflow is not allow-listed. Configure GITHUB_ALLOWED_WORKFLOWS after reviewing the workflow file." });
    const data = await gh("/repos/" + c.owner + "/" + c.repo + "/actions/workflows?per_page=100");
    const wf = (data.workflows || []).find(w => w.path === file && w.state === "active");
    if (!wf) return res.status(404).json({ error: "Allow-listed active workflow not found." });
    appendLocalLog("audit.json", { actor: req.session.username, action: "workflow_dispatch_requested", workflow: file });
    await gh("/repos/" + c.owner + "/" + c.repo + "/actions/workflows/" + wf.id + "/dispatches", {
      method: "POST", body: JSON.stringify({ ref: String(req.body?.ref || "main"), inputs: req.body?.inputs || {} })
    });
    res.json({ ok: true, message: "Workflow dispatch requested. Check Actions for its run status." });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

async function setGithubSecret(name, value) {
  await sodium.ready;
  const c = githubConfig();
  const base = "/repos/" + c.owner + "/" + c.repo + "/actions/secrets/";
  const key = await gh(base + "public-key");
  const sealed = sodium.crypto_box_seal(sodium.from_string(value), sodium.from_base64(key.key, sodium.base64_variants.ORIGINAL));
  const encrypted_value = sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
  await gh(base + encodeURIComponent(name), { method: "PUT", body: JSON.stringify({ encrypted_value, key_id: key.key_id }) });
}
app.post("/api/github/publishing",requireAuth,sameOrigin,async(req,res)=>{const mode=String(req.body?.mode||"");if(!["stop","resume"].includes(mode))return res.status(400).json({error:"Invalid action."});try{await setPublishingState(mode==="stop",req.session.username);res.json({ok:true,message:mode==="stop"?"Emergency stop written to GitHub Actions repository variables. Future workflow checks should block uploads; an upload already in progress cannot be cancelled.":"Publishing variables enabled for future runs. Verify the channel, credentials and release timing before unattended publishing."});}catch(e){res.status(502).json({error:e.message+" The GitHub token needs repository Actions variables read/write permission."});}});

app.get("/auth/youtube", requireAuth, (req, res) => {
  try {
    const oauth = oauthClient();
    const state = crypto.randomBytes(24).toString("hex");
    req.session.youtubeOAuthState = state;
    const url = oauth.generateAuthUrl({
      access_type: "offline", prompt: "consent", state,
      scope: ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
    });
    res.redirect(url);
  } catch (e) { res.status(503).send("YouTube OAuth setup needed: " + e.message); }
});
app.get("/auth/youtube/callback", requireAuth, async (req, res) => {
  if (!req.query.state || !timingSafeString(req.query.state, req.session.youtubeOAuthState)) return res.status(400).send("OAuth state mismatch. Return to the admin dashboard and retry.");
  delete req.session.youtubeOAuthState;
  if (req.query.error) return res.status(400).send("Google authorization was not completed. Return to the admin dashboard.");
  try {
    const oauth = oauthClient();
    const { tokens } = await oauth.getToken(String(req.query.code || ""));
    if (!tokens.refresh_token) {
      try { const existing = readTokens(); tokens.refresh_token = existing.refresh_token; } catch {}
    }
    if (!tokens.refresh_token && !process.env.YOUTUBE_REFRESH_TOKEN) return res.status(400).send("Google did not return a refresh token. Remove this app from Google Account permissions and connect again with consent.");
    saveTokens(tokens);
    res.redirect("/?youtube=connected");
  } catch (e) { res.status(502).send("YouTube connection failed: " + e.message); }
});

app.post("/api/youtube/upload", requireAuth, sameOrigin, upload.single("video"), async (req, res) => {
  const f = req.file;
  if (!f) return res.status(400).json({ error: "Choose a video file." });
  try {
    const title = String(req.body.title || "").trim();
    const description = String(req.body.description || "").trim();
    const privacyStatus = String(req.body.privacyStatus || "private");
    const language = String(req.body.language || "en");
    const categoryId = String(req.body.categoryId || "22");
    if (!title || title.length > 100) throw new Error("Title is required and must be at most 100 characters.");
    if (description.length > 5000) throw new Error("Description must be at most 5,000 characters.");
    if (!["private", "unlisted", "public"].includes(privacyStatus)) throw new Error("Invalid visibility.");
    if (!["en", "ml"].includes(language)) throw new Error("Language must be English or Malayalam.");
    const { youtube } = getYoutubeClient();
    const result = await youtube.videos.insert({
      part: ["snippet", "status"],
      requestBody: {
        snippet: { title, description, categoryId, defaultLanguage: language, defaultAudioLanguage: language },
        status: { privacyStatus, selfDeclaredMadeForKids: false }
      },
      media: { body: fs.createReadStream(f.path) }
    });
    try { appendLocalLog("upload-history.json", { actor: req.session.username, title, videoId: result.data.id, url: result.data.id ? "https://www.youtube.com/watch?v=" + result.data.id : null, privacyStatus, language, status: "accepted" }); appendLocalLog("audit.json", { actor: req.session.username, action: "youtube_upload_accepted", videoId: result.data.id, privacyStatus }); } catch (e) { console.error("Upload history write failed:", e.message); }
    res.json({ ok: true, videoId: result.data.id, url: result.data.id ? "https://www.youtube.com/watch?v=" + result.data.id : null, privacyStatus, message: "Upload accepted by YouTube. Verify processing and visibility in YouTube Studio." });
  } catch (e) {
    res.status(502).json({ error: e.message || "YouTube upload failed." });
  } finally {
    fs.promises.unlink(f.path).catch(() => {});
  }
});

app.get("/api/youtube/channel", requireAuth, async (_req, res) => {
  try {
    const { youtube } = getYoutubeClient();
    const ch = await youtube.channels.list({ part: ["snippet", "statistics"], mine: true, maxResults: 1 });
    const c = ch.data.items?.[0];
    if (!c) return res.status(404).json({ error: "No YouTube channel was returned for this Google account." });
    res.json({ id: c.id, title: c.snippet?.title, subscribers: c.statistics?.subscriberCount, views: c.statistics?.viewCount, videos: c.statistics?.videoCount });
  } catch (e) { res.status(502).json({ error: e.message }); }
});

app.use(express.static(PUBLIC, { index: "index.html", maxAge: process.env.NODE_ENV === "production" ? "1h" : 0 }));
app.use((err, _req, res, _next) => {
  console.error(err.message);
  res.status(err instanceof multer.MulterError ? 413 : 400).json({ error: err.message || "Request failed." });
});
app.listen(PORT, () => console.log("Swarnam4U admin listening on port " + PORT));
