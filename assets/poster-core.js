/* Poster rate logic (pure functions, no DOM). Used by poster.js and tests/poster.test.js */
(function(root,f){var m=f();if(typeof module==="object"&&module.exports)module.exports=m;else root.PosterCore=m})(this,function(){
"use strict";
var PAWAN=8, STALE_H=24;
/* Rounding policy: published board rates (22K, 18K, silver) are shown exactly as published.
   Purities the board does not publish (14K, 9K) are calculated from the 22K board rate by
   purity ratio and rounded to the nearest Rs 10. An optional data/poster-config.json can
   override any row with the shop's own rate. */
var DERIVED={"14K":[585,"14K · 585"],"9K":[375,"9K · 375"]};
function num(v){v=Number(v);return isFinite(v)&&v>0?v:null}
function r10(x){return Math.round(x/10)*10}
function same(e){return !!(e&&num(e.today)&&num(e.yesterday)&&Number(e.today)===Number(e.yesterday))}
/* Daily template rotation: Design 1 on the anchor date (IST), +1 per IST calendar day, wraps after n. Pure date maths, no randomness. */
function istYMD(d){var p=new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(d).split("-");return Date.UTC(+p[0],+p[1]-1,+p[2])}
function pickIndex(now,anchor,n){var a=anchor.split("-"),days=Math.round((istYMD(now)-Date.UTC(+a[0],+a[1]-1,+a[2]))/864e5);return ((days%n)+n)%n}
function build(data,cfg){
  var o=(cfg&&cfg.overrides)||{},g=(data&&data.gold)||{},s=(data&&data.silver)||{};
  var g22=num(o["22K"])||num(g["22K · 916"]&&g["22K · 916"].today),g18=num(o["18K"])||num(g["18K · 750"]&&g["18K · 750"].today);
  var ag=num(o["SILVER"])||num(s["Silver · 999"]&&s["Silver · 999"].today);
  if(!g22||!ag||!data||!data.updated||isNaN(new Date(data.updated)))return {ok:false,error:"A verified 22K gold and silver rate is not available yet."};
  var rows=[{k:"22K",sub:"(916)",u:["1G","8G"],v:[g22,g22*PAWAN],src:"board",unch:!o["22K"]&&same(g["22K · 916"])}];
  if(g18)rows.push({k:"18K",u:["1G","8G"],v:[g18,g18*PAWAN],src:"board",unch:!o["18K"]&&same(g["18K · 750"])});
  ["14K","9K"].forEach(function(k){var v=num(o[k])||r10(g22*DERIVED[k][0]/916);rows.push({k:k,u:["1G","8G"],v:[v,v*PAWAN],src:o[k]?"config":"calculated"})});
  rows.push({k:"SILVER",silver:true,u:["1G","10G"],v:[ag,ag*10],src:"board"});
  var ts=new Date(data.updated);
  return {ok:true,rows:rows,updated:ts,stale:(Date.now()-ts)>STALE_H*36e5,source:data.source||"AKGSMA Kerala"};
}
function inr(n){var r=Math.round(n*100)/100;return "₹ "+r.toLocaleString("en-IN",{maximumFractionDigits:2})}
function ist(d,o){return new Intl.DateTimeFormat("en-IN",Object.assign({timeZone:"Asia/Kolkata"},o)).format(d)}
function dateLabel(d){return ist(d,{day:"2-digit",month:"short",year:"numeric"}).toUpperCase().replace(/,/g,"")}
function dayLabel(d){return ist(d,{weekday:"long"}).toUpperCase()}
function timeLabel(d){return ist(d,{hour:"numeric",minute:"2-digit",hour12:true}).toUpperCase().replace(/\s+/g," ")+" IST"}
function waLink(phone,text){var n=String(phone).replace(/\D/g,"");if(n.length===10)n="91"+n;return "https://wa.me/"+(text===undefined?n:"?text="+encodeURIComponent(text))}
function summary(p,biz){
  var L=["*"+biz+" – Kozhikode*","Rates as of "+dateLabel(p.updated)+", "+timeLabel(p.updated)+(p.stale?" (may be out of date)":"")];
  p.rows.forEach(function(r){L.push(r.k+(r.sub?" "+r.sub:"")+": "+inr(r.v[0])+"/"+r.u[0].toLowerCase()+" · "+inr(r.v[1])+"/"+r.u[1].toLowerCase())});
  return L.join("\n")}
return {pickIndex:pickIndex,build:build,inr:inr,dateLabel:dateLabel,dayLabel:dayLabel,timeLabel:timeLabel,waLink:waLink,summary:summary,PAWAN:PAWAN};
});
