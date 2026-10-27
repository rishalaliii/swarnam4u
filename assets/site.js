/* Swarnam4U shared helpers: rate loading, formatting, metal picker, status stamp. */
(function(){
"use strict";
var DATA_URL="data/rates.json", REFRESH_MS=60*1000, LIVE_MS=2*60*1000, STALE_H=24;
var META={
  gold:{name:"Gold",sym:"Au",feat:"22K · 916"},
  silver:{name:"Silver",sym:"Ag",feat:"Silver · 925"},
  platinum:{name:"Platinum",sym:"Pt",feat:"Platinum · 950"}
};
var S=window.Swarnam={META:META,data:null,error:false,metal:"gold",subs:[]}, raw=null;
var $=S.$=function(id){return document.getElementById(id)};

S.inr=function(n){var r=Math.round(n);return Math.abs(n-r)<.005?"₹"+r.toLocaleString("en-IN"):S.inr2(n)};   /* whole rupees for gold, paise shown when present (silver 925 = 212.75) */
S.inr2=function(n){return "₹"+Number(n).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})};
S.fmtDate=function(d,o){return new Date(d+"T00:00:00").toLocaleDateString("en-IN",o||{day:"2-digit",month:"short",year:"numeric"})};
S.fmtStamp=function(iso){return new Date(iso).toLocaleString("en-IN",{day:"numeric",month:"short",year:"numeric",hour:"numeric",minute:"2-digit",timeZone:"Asia/Kolkata"})+" IST"};
S.hasRates=function(){var d=S.data;
  return !!(d&&d.updated&&!isNaN(new Date(d.updated))&&["gold","silver","platinum"].some(function(k){return d[k]&&Object.keys(d[k]).length}))};
S.isStale=function(){
   if(!S.hasRates())return false;
   var today=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"});
   var meta=META[S.metal]||META.gold,entry=(S.data[S.metal]||{})[meta.feat];
   if(entry&&entry.date)return entry.date!==today;
   return (Date.now()-new Date(S.data.updated))>STALE_H*36e5;
 };
/* change vs previous rate; null when no previous value is known */
S.change=function(v){
  if(!v||v.yesterday==null||!v.yesterday)return null;
  var d=v.today-v.yesterday;
  return {d:d,p:d/v.yesterday*100,cls:d>=0?"up":"down",sg:d>=0?"+":"−",arrow:d>=0?"▲":"▼"};
};

/* selected metal is remembered across pages (storage may be unavailable) */
(function(){
  var q=new URLSearchParams(location.search).get("metal"), m=null;
  try{m=localStorage.getItem("s4u-metal")}catch(e){}
  S.metal=META[q]?q:(META[m]?m:"gold");
})();
function saveMetal(m){try{localStorage.setItem("s4u-metal",m)}catch(e){}}

S.picker=function(root,cb){
  var tabs=[].slice.call(root.querySelectorAll(".ingot"));
  function sel(m,focus,user){
    S.metal=m;saveMetal(m);
    tabs.forEach(function(t){var on=t.dataset.m===m;t.setAttribute("aria-selected",on?"true":"false");t.tabIndex=on?0:-1;if(on&&focus)t.focus()});
    cb(m);if(user)S.tab();
  }
  tabs.forEach(function(t,i){
    t.addEventListener("click",function(){sel(t.dataset.m,false,true)});
    t.addEventListener("keydown",function(e){
      var n=null;
      if(e.key==="ArrowRight")n=(i+1)%tabs.length;else if(e.key==="ArrowLeft")n=(i+tabs.length-1)%tabs.length;
      if(n!==null){e.preventDefault();sel(tabs[n].dataset.m,true,true)}
    });
  });
  sel(S.metal);
};

S.renderStamp=function(){
  var el=$("stamp");if(!el)return;var box=el.parentNode;
  if(S.busy&&!S.liveAt){box.dataset.s=S.hasRates()?"stale":"none";el.textContent=S.hasRates()?"Showing last known rates · checking AKGSMA and Kerala sources for the latest…":"Fetching latest rates from AKGSMA and Kerala sources…"}
  else if(S.hasRates()&&S.liveFail&&!S.liveAt){box.dataset.s="stale";el.textContent="Live sources unreachable · showing last known rates from "+S.fmtStamp(S.data.updated)+" · tap Refresh"}
  else if(S.hasRates()){
    var st=S.isStale();box.dataset.s=st?"stale":"ok";
    var base=S.data.live?"Live rates checked "+new Date(S.data.live).toLocaleTimeString("en-IN",{hour:"numeric",minute:"2-digit",second:"2-digit"}):(st?"Last verified ":"Updated ")+S.fmtStamp(S.data.updated)+" · "+(S.data.source||"AKGSMA Kerala")+(st?" · may be out of date":"");
    el.textContent=base;
  }else if(S.error&&!S.data){box.dataset.s="none";el.textContent="Could not load rates. Retrying shortly."}
  else if(S.data){box.dataset.s="none";el.textContent=S.liveFail?"Live sources unreachable right now · tap Refresh to retry":"Rates unavailable · waiting for the first verified update"}
  else{box.dataset.s="none";el.textContent="Loading rates…"}
  var b=$("refreshBtn");
  if(!b){b=document.createElement("button");b.id="refreshBtn";b.className="refresh";b.type="button";b.textContent="Refresh";
    b.addEventListener("click",function(){S.lastLive=0;S.refresh(true)});box.appendChild(b)}
  b.disabled=S.busy;b.textContent=S.busy?"Updating…":"Refresh";b.className="refresh"+(S.busy?" spin":"");
};

/* ---------- live fetching: tried in order until one returns parseable rates ---------- */
/* OPTIONAL fastest path: paste your deployed Cloudflare Worker URL (see worker/README.md), e.g. "https://s4u-rates.yourname.workers.dev". Leave "" to use public relays only. */
var WORKER="";
var AK="https://akgsma.com";
var ROUTES=[
  function(u){return WORKER?WORKER+"/?url="+encodeURIComponent(u):u},   /* own proxy when configured, else direct */                                                       /* direct (works only if the site allows CORS) */
  function(u){return "https://api.allorigins.win/raw?url="+encodeURIComponent(u)},
  function(u){return "https://corsproxy.io/?"+encodeURIComponent(u)},
  function(u){return "https://r.jina.ai/"+u},                                  /* text mirror, CORS enabled */
  function(u){return "https://api.codetabs.com/v1/proxy?quest="+encodeURIComponent(u)}
];
var PAT=[ /* group, label, regex, plausible range (INR/gram) — mirrors scripts/fetch_rates.py */
  ["gold","24K · 999",/\b24\s*(?:K|Kt|Carat|Karat)\b/i,1000,100000],["gold","22K · 916",/\b22\s*(?:K|Kt|Carat|Karat)\b/i,1000,100000],
  ["gold","18K · 750",/\b18\s*(?:K|Kt|Carat|Karat)\b/i,1000,100000],["gold","14K · 585",/\b14\s*(?:K|Kt|Carat|Karat)\b/i,1000,100000],
  ["silver","Silver · 999",/\bsilver\b/i,10,2000],["platinum","Platinum · 950",/\bplatinum\b/i,500,50000]];
/* AKGSMA publishes exactly: "22K916 (1gm) - ₹ 13515", "18K750 (1gm) - ₹ 11060", "Silver (1gm) - ₹ 230" (no 24K, no platinum). Matched exactly so site-name words or dates are never read as rates. */
var GAP="\\s*\\(\\s*1\\s*gm\\s*\\)\\W{0,8}(\\d[\\d,]*(?:\\.\\d+)?)";
var AKPAT=[["gold","22K · 916",new RegExp("22\\s*K\\s*916"+GAP,"i"),1000,100000],["gold","18K · 750",new RegExp("18\\s*K\\s*750"+GAP,"i"),1000,100000],
  ["silver","Silver · 999",new RegExp("(?<!Marked\\s)(?<!925\\s)\\bSilver"+GAP,"i"),10,2000],
  ["silver","Silver · 925",new RegExp("925\\s*Hall\\s*Marked\\s*Silver"+GAP,"i"),10,5000]];
var CODES=[999,925,916,950,900,850,800,750,585], STOP=/\b(?:\d{2}\s*(?:K|Kt|Carat|Karat)|gold|silver|platinum)\b/i, MAXJ=.25;
function pick(text,rx,lo,hi){
  /* pass 1: rupee-prefixed numbers only; pass 2: plain numbers (never a year) */
  for(var pass=0;pass<2;pass++){
    var g=new RegExp(rx.source,"gi"),m;
    while((m=g.exec(text))){
      var win=text.slice(g.lastIndex,g.lastIndex+120).replace(/^\s*(?:gold|silver|platinum)\b/i,""),s=STOP.exec(win);if(s)win=win.slice(0,s.index);
      var nums=pass===0?(win.match(/(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?/g)||[]).map(function(x){return x.replace(/^(?:₹|Rs\.?|INR)\s*/,"")}):(win.match(/\d[\d,]*(?:\.\d+)?/g)||[]);
      for(var i=0;i<nums.length;i++){var v=parseFloat(nums[i].replace(/,/g,""));
        if(isNaN(v)||CODES.indexOf(v)>=0||v<lo||v>hi||(pass&&v>=1990&&v<=2100))continue;return v}
    }
  }return null;
}
function timeout(ms,p){return new Promise(function(res,rej){var t=setTimeout(function(){rej(new Error("timeout"))},ms);p.then(function(v){clearTimeout(t);res(v)},function(e){clearTimeout(t);rej(e)})})}
function anyOf(ps){return new Promise(function(res,rej){var n=ps.length,done=false;ps.forEach(function(p){p.then(function(v){if(!done){done=true;res(v)}},function(){if(--n===0)rej(new Error("all failed"))})})})}
/* all routes fire at the same moment; the first good answer wins (no waiting on slow/blocked ones) */
S.diag={};
function viaRoutes(url,valid){
  var ctl=new AbortController(),errs=[],t0=Date.now();
  return anyOf(ROUTES.map(function(r,i){
    return timeout(5000,fetch(r(url),{cache:"no-store",signal:ctl.signal})).then(function(x){if(!x.ok)throw new Error("HTTP "+x.status);return x.text()})
      .then(function(h){var t=new DOMParser().parseFromString(h,"text/html");var x=t.body?t.body.textContent.replace(/\s+/g," "):"";
        if(x.length<150)throw new Error("empty");
        if(valid&&!valid(x))throw new Error("not the rate page");     /* an error/captcha page from a relay must never win the race */
        S.diag[url]="ok via relay "+(i+1)+" in "+(Date.now()-t0)+" ms";return x})
      .catch(function(e){errs[i]=(e&&e.message)||"failed";throw e});
  })).then(function(x){try{ctl.abort()}catch(e){}return x},function(e){try{ctl.abort()}catch(ignore){}S.diag[url]="FAILED: "+errs.map(function(m,i){return "relay "+(i+1)+" "+m}).join(", ");throw e});
}
function isTodayIstDate(iso){
  return iso===new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"});
}
function currentBoardDateFromAkgsma(text){
  var m=/Today'?s Rate\s*\((\d{1,2})\/(\d{1,2})\/(\d{4})\)/i.exec(text);
  if(!m)return null;
  return m[3]+"-"+String(Number(m[2])).padStart(2,"0")+"-"+String(Number(m[1])).padStart(2,"0");
}
var okAK=function(x){
  return currentBoardDateFromAkgsma(x)===new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"})
    && /22\s*K\s*916[\s\S]{0,40}1\s*gm/i.test(x);
};
var okLiveGold=function(x){
  var m=/\b\w+day,\s*(\d{1,2}) ([A-Z][a-z]+) (\d{4})\b/.exec(x);
  if(!m)return false;
  var months={January:"01",February:"02",March:"03",April:"04",May:"05",June:"06",July:"07",August:"08",September:"09",October:"10",November:"11",December:"12"};
  var iso=m[3]+"-"+(months[m[2]]||"00")+"-"+String(Number(m[1])).padStart(2,"0");
  return isTodayIstDate(iso)&&/AKGSMA/i.test(x)&&/22\s+Karat\s+Gold/i.test(x);
};
var okPage=function(x){return /(?:₹|Rs\.?)\s*\d/.test(x)};
/* returns number of rates applied */
S.ov={};S.liveAt=null;
var BACKUP0={
  gold:[["LiveGold Kerala (AKGSMA board rate)","https://www.livegoldkerala.com/kozhikode"],["LiveGold Kerala (AKGSMA board rate)","https://www.livegoldkerala.com/"],["Goodreturns Kerala","https://www.goodreturns.in/gold-rates/kerala.html"],["BankBazaar Kerala","https://www.bankbazaar.com/gold-rate-kerala.html"]],
  silver:[["Goodreturns Kerala","https://www.goodreturns.in/silver-rates/kerala.html"],["BankBazaar Kerala","https://www.bankbazaar.com/silver-rate-kerala.html"]],
  platinum:[["Goodreturns Kerala","https://www.goodreturns.in/platinum-rate-in-kerala.html"],["BankBazaar Kerala","https://www.bankbazaar.com/platinum-price-kerala.html"]]
};
var BACKUP={};
S.metals=S.metals||["gold","silver","platinum"];
function pruneBackup(){BACKUP={};S.metals.forEach(function(m){if(BACKUP0[m])BACKUP[m]=BACKUP0[m]})}
function apply(text,only,src){
  var n=0,today=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"}),ak=/AKGSMA/.test(src);
  (ak?AKPAT:PAT).forEach(function(p){
    if(only&&p[0]!==only)return;
    var o=S.data[p[0]][p[1]];
    if(!ak&&o&&o.date===today&&/live/.test(o.source||""))return;      /* never let a backup overwrite a live value */
    var v;
    if(ak){var m=p[2].exec(text);v=m?parseFloat(m[1].replace(/,/g,"")):null;if(v!=null&&(isNaN(v)||v<p[3]||v>p[4]))v=null}
    else v=pick(text,p[2],p[3],p[4]);
    if(v==null)return;
    if(o&&o.today&&Math.abs(v-o.today)/o.today>MAXJ)return;
    var y=!o?null:(o.date===today?o.yesterday:o.today);
    var e={today:v,yesterday:y,date:today,source:src};S.data[p[0]][p[1]]=e;S.ov[p[0]+"|"+p[1]]=e;n++;
  });return n;
}
function derive(){
  var d=S.data,today=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"}),b=d&&d.gold&&d.gold["22K · 916"],n=0;
  var sb=d.silver&&d.silver["Silver · 999"];
  if(sb&&sb.date===today&&/live/.test(sb.source||"")){
    var sbase=(sb.source||"").replace(/\s*\(live\)\s*$/,"")+" (calculated from 999) (live)";
    [["Silver · 925",.925],["Silver · 800",.8]].forEach(function(x){
      var o=d.silver[x[0]];if(o&&o.date===today&&/live/.test(o.source||"")&&!/calculated/.test(o.source))return;     /* quoted 925 beats calculated */
      var v=Math.round(sb.today*x[1]*100)/100,y=!o?null:(o.date===today?o.yesterday:o.today);
      var e={today:v,yesterday:y,date:today,source:sbase};d.silver[x[0]]=e;S.ov["silver|"+x[0]]=e;n++;});
  }
  if(!b||b.date!==today||!/live/.test(b.source||""))return n;
  var base=(b.source||"").replace(/\s*\(live\)\s*$/,"")+" (calculated from 22K) (live)";
  [["24K · 999",24/22],["14K · 585",585/916],["18K · 750",750/916]].forEach(function(x){
    var o=d.gold[x[0]];
    if(x[0]==="18K · 750"&&o&&o.date===today&&/live/.test(o.source||"")&&!/calculated/.test(o.source))return;   /* quoted 18K beats calculated */
    var v=Math.round(b.today*x[1]),y=!o?null:(o.date===today?o.yesterday:o.today);
    var e={today:v,yesterday:y,date:today,source:base};d.gold[x[0]]=e;S.ov["gold|"+x[0]]=e;n++;
  });return n;
}
/* returns number of rates applied. AKGSMA for everything; if it lacks silver/platinum (or is down) those metals try their own backup page, all in parallel. */
S.live=function(ready){
  ready=ready||Promise.resolve();
  function ensure(){if(!S.data)S.data={source:"AKGSMA Kerala",currency:"INR",unit:"gram",updated:null,gold:{},silver:{},platinum:{},history:{gold:[],silver:[],platinum:[]}}}
  var today=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"});
  function fresh(m){var r=S.data[m]||{};return Object.keys(r).some(function(k){return r[k].date===today&&/live/.test(r[k].source||"")})}
  /* fastest and most reliable: our own Worker fetches and parses server-side (see worker/README.md) */
  var api=!WORKER?Promise.resolve(0):timeout(6000,fetch(WORKER+"/?api=rates",{cache:"no-store"})).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()}).then(function(j){
    return ready.then(function(){ensure();var n=0;
      [["gold","g"],["silver","s"]].forEach(function(g){if(j.date!==today)throw new Error("rate API board date does not match today in Kerala");var o=j[g[0]]||{};Object.keys(o).forEach(function(k){var v=+o[k];if(!v)return;
        var old=S.data[g[0]][k],y=!old?null:(old.date===today?old.yesterday:old.today);
        var e={today:v,yesterday:y,date:today,source:(j.source||"AKGSMA Kerala")+(/\*$/.test(k)?"":"")+" (live)"};
        if(j.calc&&j.calc.indexOf(k)>=0)e.source=(j.source||"AKGSMA Kerala")+" (calculated from 22K) (live)";
        S.data[g[0]][k]=e;S.ov[g[0]+"|"+k]=e;n++})});return n})}).catch(function(){return 0});
  var main=viaRoutes(AK,okAK).then(function(t){return ready.then(function(){ensure();return apply(t,null,"AKGSMA Kerala (live)")})}).catch(function(){return 0});
  pruneBackup();
  var backs=Object.keys(BACKUP).map(function(m){
    /* backup pages are requested ONLY if AKGSMA did not already give this metal live today (saves ~30 requests per refresh) */
    return Promise.all([main,ready,api]).then(function(){
      if(fresh(m))return 0;
      return Promise.all(BACKUP[m].map(function(b){var validator=/livegoldkerala\.com/i.test(b[1])?okLiveGold:okPage;return viaRoutes(b[1],validator).then(function(t){return {t:t,n:b[0]}},function(){return null})}))
        .then(function(rs){var tot=0;for(var i=0;i<rs.length;i++){if(rs[i]&&!fresh(m))tot+=apply(rs[i].t,m,rs[i].n+" (live)")}return tot})
    }).catch(function(){return 0});
  });
  return Promise.all([api,main].concat(backs)).then(function(a){
    var n=a.reduce(function(x,y){return x+y},0);
    /* purities the board does not publish are calculated from its 22K rate, exactly like Asian Jewellery does */
    n+=derive();
    S.liveFail=!n;
    if(n){S.liveAt=new Date().toISOString();S.data.live=S.liveAt;S.data.updated=S.liveAt}   /* "last updated" = the moment fresh rates were really fetched */
    return n;
  });
};
S.renderDiag=function(){var e=$("diag");if(!e)return;e.textContent=Object.keys(S.diag).map(function(u){return u.replace(/^https:\/\//,"")+"  →  "+S.diag[u]}).join("\n")};
S.busy=false;
function save(){if(!S.hasRates())return;try{localStorage.setItem("s4u-cache",JSON.stringify(S.data))}catch(e){}}
S.load=function(){
  return timeout(6000,fetch(DATA_URL+"?t="+Date.now(),{cache:"no-store"}))
    .then(function(r){if(!r.ok)throw new Error(r.status);return r.text()})
    .then(function(t){S.error=false;if(t===raw)return false;
      var nd=JSON.parse(t),live=S.data&&S.data.live;raw=t;
      ["gold","silver","platinum"].forEach(function(g){var old=(S.data&&S.data[g])||{};nd[g]=nd[g]||{};
        Object.keys(old).forEach(function(k){var n=nd[g][k];if(!n||(n.date||"")<(old[k].date||""))nd[g][k]=old[k]})});   /* keep newer saved/live values over an older or empty file */
      if(S.data&&S.data.updated&&(!nd.updated||new Date(nd.updated)<new Date(S.data.updated)))nd.updated=S.data.updated;
      Object.keys(S.ov).forEach(function(k){var a=k.split("|");nd[a[0]]=nd[a[0]]||{};var o=nd[a[0]][a[1]];
        if(!o||o.date<=S.ov[k].date)nd[a[0]][a[1]]=S.ov[k]});                  /* live values outrank an older file */
      if(S.liveAt){nd.live=S.liveAt;if(!nd.updated||new Date(nd.updated)<new Date(S.liveAt))nd.updated=S.liveAt}
      S.data=nd;save();return true})
    .catch(function(){S.error=!S.data;return false})
    .then(function(changed){S.renderStamp();if(changed)S.subs.forEach(function(f){f()})});
};
/* One live fetch parses gold, silver AND platinum together, so switching tabs never waits on the network. */
S.refresh=function(force){
  var gap=force?0:LIVE_MS;
  if(S.busy||(S.lastLive&&Date.now()-S.lastLive<gap))return Promise.resolve();
  S.busy=true;S.renderStamp();
  var fileP=S.load();                                       /* file and live run in parallel */
  var liveP=S.live(fileP).then(function(n){if(n){save();S.subs.forEach(function(f){f()})}return n});
  return Promise.all([fileP,liveP]).then(function(){S.lastLive=Date.now();S.busy=false;S.renderStamp();S.renderDiag()},function(){S.liveFail=true;S.lastLive=Date.now();S.busy=false;S.renderStamp();S.renderDiag();return 0});
};
/* switching metal: show it instantly from memory, and quietly re-check in the background */
S.tab=function(){S.refresh(true)};

S.start=function(cb){S.subs.push(cb);
  /* open: paint the last real rates this browser saved (never invented) so the page is never blank, and fetch the latest at the same instant */
  try{var k=localStorage.getItem("s4u-cache");if(k&&!S.data){var c=JSON.parse(k);if(c&&c.updated){S.data=c;delete S.data.live;S.renderStamp();cb()}}}catch(e){}
  S.refresh(true);                                           /* file + live check start immediately */
  setInterval(function(){if(!document.hidden)S.refresh(false)},REFRESH_MS);
  document.addEventListener("visibilitychange",function(){if(!document.hidden)S.refresh(false)});
  window.addEventListener("online",function(){S.refresh(true)});
  /* IST midnight: new date -> fetch fresh rates and redraw everything (poster date/design, trends range) without a reload */
  var day=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"});
  setInterval(function(){var d=new Date().toLocaleDateString("en-CA",{timeZone:"Asia/Kolkata"});
    if(d!==day){day=d;S.lastLive=0;S.subs.forEach(function(f){f()});S.refresh(true)}},15000);
  window.addEventListener("focus",function(){S.refresh(false)});
};

/* ---------- realtime date and time (IST) at the top of every page ---------- */
(function(){
  function mount(){
    var h=document.querySelector("header.nav");if(!h||document.getElementById("clock"))return;
    var bar=document.createElement("div");bar.className="clockbar";
    bar.innerHTML='<div class="wrap"><span class="live-dot"></span><span id="clock" aria-live="off"></span></div>';
    h.insertBefore(bar,h.firstChild);
    var d=new Intl.DateTimeFormat("en-IN",{weekday:"long",day:"numeric",month:"long",year:"numeric",timeZone:"Asia/Kolkata"});
    var t=new Intl.DateTimeFormat("en-IN",{hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:true,timeZone:"Asia/Kolkata"});
    var el=bar.querySelector("#clock");
    function tick(){var n=new Date();el.textContent=d.format(n)+" · "+t.format(n).toUpperCase()+" IST"}
    tick();setInterval(tick,1000);
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",mount);else mount();
})();

document.addEventListener("DOMContentLoaded",function(){var y=$("yr");if(y)y.textContent=new Date().getFullYear()});
})();
