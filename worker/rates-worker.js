// Cloudflare Worker for Swarnam4U. Same method as the Asian Jewellery server (rates_sync.py), run at the edge:
//   GET /?api=rates      -> JSON rates parsed server-side from AKGSMA (primary) and LiveGold Kerala (backup), cached 60 s
//   GET /?url=<https..>  -> CORS-enabled, cached relay for allow-listed pages (used by the site's backup pages)
// Deploy: dash.cloudflare.com > Workers & Pages > Create > paste this > Deploy. Put the URL in WORKER in assets/site.js.
const ALLOW = ["akgsma.com", "www.akgsma.com", "www.goodreturns.in", "www.bankbazaar.com", "stablemoney.in", "livegoldkerala.com", "www.livegoldkerala.com"];
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET", "Cache-Control": "public, max-age=30" };
const UA = "Mozilla/5.0 (compatible; Swarnam4URateCheck/1.0)";
const MON = { January: 1, February: 2, March: 3, April: 4, May: 5, June: 6, July: 7, August: 8, September: 9, October: 10, November: 11, December: 12 };

export function text(h) {
  h = h.replace(/<!--[\s\S]*?-->|<(script|style)\b[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ");
  h = h.replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&#8377;/g, "₹").replace(/&#39;|&rsquo;/g, "'");
  return h.replace(/\s+/g, " ");
}
const num = (t, re) => { const m = t.match(re); return m ? parseFloat(m[1].replace(/,/g, "")) : null; };
const iso = (y, m, d) => `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const GAP = String.raw`\s*\(\s*1\s*gm\s*\)\s*[-–:]?\s*(?:₹|Rs\.?)?\s*([\d,]+(?:\.\d+)?)`;

export function parseAkgsma(t) {
  const d = t.match(/Today'?s Rate\s*\((\d{1,2})\/(\d{1,2})\/(\d{4})\)/i);
  if (!d) throw new Error("rate date not found");
  return { date: iso(d[3], d[2], d[1]), g916: num(t, new RegExp("22\\s*K\\s*916" + GAP, "i")), g750: num(t, new RegExp("18\\s*K\\s*750" + GAP, "i")),
           s999: num(t, new RegExp("(?<!Marked\\s)(?<!925\\s)\\bSilver" + GAP, "i")),
           s925: num(t, new RegExp("925\\s*Hall\\s*Marked\\s*Silver" + GAP, "i")) };
}
export function parseLivegold(t) {
  if (!t.includes("AKGSMA")) throw new Error("AKGSMA board label missing");
  const d = t.match(/\b\w+day,\s*(\d{1,2}) ([A-Z][a-z]+) (\d{4})/);
  if (!d || !MON[d[2]]) throw new Error("rate date not found");
  return { date: iso(d[3], MON[d[2]], d[1]), g916: num(t, /22 Karat Gold.{0,60}?₹\s*([\d,]+)/), g750: num(t, /18 Karat\s*750.{0,40}?₹\s*([\d,]+)/),
           s999: num(t, /Ag 999.{0,60}?₹\s*([\d,]+(?:\.\d+)?)\s*\/\s*g/) };
}
export function validate(d) {
  const { g916: g, g750: g7, s999: s } = d;
  if (!g && !s) throw new Error("no rates found");
  if (g && !(g > 3000 && g < 60000)) throw new Error("22K outside plausible range");
  if (g && g7 && Math.abs(g7 / (g * 750 / 916) - 1) > 0.04) throw new Error("18K/22K ratio implausible");
  if (s && !(s > 20 && s < 5000)) throw new Error("silver outside plausible range");
  return d;
}
const SOURCES = [["AKGSMA Kerala", "https://akgsma.com/", parseAkgsma], ["LiveGold Kerala (AKGSMA board rate)", "https://www.livegoldkerala.com/kozhikode", parseLivegold]];

export function build(results) {
  if (!results.length) return null;
  const top = results.map(r => r.date).sort().pop();
  const gd = results.find(r => r.date === top && r.g916);
  const sd = results.find(r => r.date === top && r.s999) || results.find(r => r.s999);
  const out = { date: top, gold: {}, silver: {}, calc: [], sources: results.map(r => r.name) };
  if (gd) {
    const g = gd.g916; out.source = gd.name;
    out.gold["22K · 916"] = Math.round(g);
    out.gold["18K · 750"] = Math.round(gd.g750 || g * 750 / 916); if (!gd.g750) out.calc.push("18K · 750");
    out.gold["24K · 999"] = Math.round(g * 24 / 22); out.gold["14K · 585"] = Math.round(g * 585 / 916);
    out.calc.push("24K · 999", "14K · 585");
  }
  if (sd) {
    const v = sd.s999; out.source = out.source || sd.name;
    out.silver["Silver · 999"] = v;
    if (sd.s925) out.silver["Silver · 925"] = sd.s925; else { out.silver["Silver · 925"] = Math.round(v * .925 * 100) / 100; out.calc.push("Silver · 925"); }
    out.silver["Silver · 800"] = Math.round(v * .8 * 100) / 100; out.calc.push("Silver · 800");
  }
  return out;
}

async function getRates(fetchFn = fetch) {
  const settled = await Promise.all(SOURCES.map(async ([name, url, parser]) => {
    try {
      const r = await fetchFn(url, { headers: { "User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9" }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = validate(parser(text(await r.text()))); d.name = name; return d;
    } catch (e) { return null; }
  }));
  return build(settled.filter(Boolean));
}

export default {
  async fetch(req) {
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    const q = new URL(req.url).searchParams;
    if (q.get("api") === "rates") {
      const out = await getRates();
      return new Response(JSON.stringify(out || { error: "no source available" }), { status: out ? 200 : 502, headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "public, max-age=30" } });
    }
    let u;
    try { u = new URL(q.get("url")); } catch { return new Response("bad url", { status: 400, headers: CORS }); }
    if (u.protocol !== "https:" || !ALLOW.includes(u.hostname)) return new Response("host not allowed", { status: 403, headers: CORS });
    const r = await fetch(u.toString(), { headers: { "User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9" }, cf: { cacheTtl: 30, cacheEverything: true } });
    return new Response(await r.text(), { status: r.status, headers: { ...CORS, "Content-Type": "text/html; charset=utf-8" } });
  },
};
export { getRates };
