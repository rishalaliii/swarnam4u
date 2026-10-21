/* Asian Jewellery poster: draws today's date + rate table over one of the 10 supplied designs (daily rotation).
   Rates come from data/rates.json / site.js; templates from data/poster-templates.json. Output keeps the design's own pixel size. */
(function(){
"use strict";
var C=PosterCore,S=Swarnam,$=S.$,PHONE="9895232441",cfg={},tpl=null,poster=null,busy=false,cache={};
var SANS='Jost,"Segoe UI",Arial,sans-serif';
function lg(c,x0,y0,x1,y1,st){var g=c.createLinearGradient(x0,y0,x1,y1);st.forEach(function(s,i){g.addColorStop(i/(st.length-1),s)});return g}
function rr(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath()}
function sp(c,t,x,y,gap,al){var w=0,a=[];for(var i=0;i<t.length;i++){a[i]=c.measureText(t[i]).width;w+=a[i]+gap}w-=gap;
  var sx=al==="left"?x:al==="right"?x-w:x-w/2;c.textAlign="left";for(i=0;i<t.length;i++){c.fillText(t[i],sx,y);sx+=a[i]+gap}return w}
function fit(c,t,font,max,size){do{c.font=font.replace("#",size);size-=2}while(c.measureText(t).width>max&&size>12);return size+2}
function row(c,r,x,y,w,h,u,t){
  var sil=r.silver,L=t.label,gold=sil?["#fff","#b9b9c1"]:L;c.save();rr(c,x,y,w,h,h*.3);
  c.fillStyle=lg(c,0,y,0,y+h,sil?t.silverPanel:t.panel);c.fill();
  c.lineWidth=3*u;c.strokeStyle=sil?lg(c,x,y,x+w,y,["#fff","#9a9a9f","#e8e8ec"]):lg(c,x,y,x+w,y+h,t.lineGrad||L);c.stroke();
  c.fillStyle=lg(c,0,y,0,y+h,gold);c.textAlign="left";c.textBaseline="alphabetic";var cy=y+h/2,lx=x+30*u;
  if(sil){c.font="800 "+68*u+"px "+SANS;c.fillText("SILVER",lx,cy+24*u)}
  else{c.font="800 "+(r.sub?78:76)*u+"px "+SANS;c.fillText(r.k,lx,cy+(r.sub?8:26)*u);
    if(r.sub){c.font="500 "+28*u+"px "+SANS;c.fillStyle=t.unit;c.fillText(r.sub,lx+14*u,cy+h*.36)}}
  var d1=x+335*u,d2=x+515*u;c.strokeStyle=t.divider;c.lineWidth=2*u;
  [d1,d2].forEach(function(dx){c.beginPath();c.moveTo(dx,y+h*.18);c.lineTo(dx,y+h*.82);c.stroke()});
  c.fillStyle=t.unit;c.font="500 "+30*u+"px "+SANS;var ux=(d1+d2)/2;
  sp(c,r.u[0],ux,cy-8*u,2*u,"center");sp(c,r.u[1],ux,cy+36*u,2*u,"center");
  var px=d2+26*u,maxw=x+w-px-24*u,f="700 #px "+SANS,a=C.inr(r.v[0]),b=C.inr(r.v[1]);
  var s=Math.min(fit(c,a,f,maxw,48*u),fit(c,b,f,maxw,48*u));
  c.fillStyle=t.price;c.font="700 "+s+"px "+SANS;c.textAlign="left";c.shadowColor="rgba(0,0,0,.45)";c.shadowBlur=5*u;
  c.fillText(a,px,cy-4*u);c.fillText(b,px,cy+s*.95-4*u);c.shadowBlur=0;
  if(r.unch){c.font="600 "+17*u+"px "+SANS;c.fillStyle=t.unit;c.textAlign="right";c.fillText("UNCHANGED",x+w-24*u,y+h*.2)}
  c.restore()}
function draw(c,W,H,img,t,L,p,now){
  var u=W/1080;c.clearRect(0,0,W,H);c.drawImage(img,0,0,W,H);c.textBaseline="alphabetic";
  /* date pill (today, IST) */
  var ph=H*L.pillH,py=H*L.pillTop,pw=W*.6,px=(W-pw)/2;rr(c,px,py,pw,ph,ph/2);c.fillStyle=lg(c,0,py,0,py+ph,t.pill);c.fill();
  c.strokeStyle="rgba(255,241,192,.8)";c.lineWidth=2*u;c.stroke();c.fillStyle=t.pillText;c.textAlign="left";
  var ds=C.dateLabel(now),dy=C.dayLabel(now),mid=py+ph/2;
  c.font="700 "+ph*.46+"px "+SANS;var dw=c.measureText(ds).width;c.font="500 "+ph*.32+"px "+SANS;var yw=sp(c,dy,0,-999,4*u,"left");
  var gap=26*u,tot=dw+gap*2+2*u+yw,sx=W/2-tot/2;
  c.font="700 "+ph*.46+"px "+SANS;c.fillText(ds,sx,mid+ph*.16);c.fillRect(sx+dw+gap,py+ph*.22,2*u,ph*.56);
  c.font="500 "+ph*.32+"px "+SANS;sp(c,dy,sx+dw+gap*2+2*u,mid+ph*.11,4*u,"left");
  /* table */
  var x=W*L.tableX,w=W-2*x,top=H*L.tableTop,bot=H*L.tableBottom,g=H*L.gap,n=p.rows.length,h=(bot-top-g*(n-1))/n;
  p.rows.forEach(function(r,i){row(c,r,x,top+i*(h+g),w,h,u,t)});
  /* honest freshness line: when the rates were really published */
  c.fillStyle=t.note;c.textAlign="center";c.font="600 "+21*u+"px "+SANS;
  sp(c,(p.stale?"LAST UPDATED ":"RATES UPDATED ")+C.dateLabel(p.updated)+", "+C.timeLabel(p.updated),W/2,H*L.noteY,3*u,"center")}
function status(t,k){var e=$("pStatus");e.textContent=t;e.dataset.k=k||""}
function loadImg(src){return cache[src]||(cache[src]=new Promise(function(res,rej){var tries=0;
  function go(){var i=new Image(),t=setTimeout(function(){i.onload=i.onerror=null;fail()},25000);
    i.onload=function(){clearTimeout(t);res(i)};i.onerror=function(){clearTimeout(t);fail()};i.decoding="async";i.src=src+(tries?"?r="+tries:"")}
  function fail(){if(++tries<3)setTimeout(go,600);else{delete cache[src];rej(new Error("Could not load the poster image. Check your connection and tap Preview / Regenerate Poster."))}}
  go()}))}
function fonts(){var f=document.fonts;if(!f||!f.load)return Promise.resolve();
  var all=Promise.all(["700 40px Jost","500 40px Jost","800 40px Jost"].map(function(x){return f.load(x).catch(function(){})}));
  return Promise.race([all,new Promise(function(r){setTimeout(r,1500)})])}   /* never wait more than 1.5 s for web fonts: fallback font is used */
function todayIndex(now){var n=cfg.tpl.templates.length,i=C.pickIndex(now,cfg.tpl.anchorDate,n),q=/[?&]design=(\d+)/.exec(location.search);if(q&&+q[1]>=1&&+q[1]<=n)i=+q[1]-1;return i}   /* ?design=N previews a specific design */
function render(){
  var p=C.build(S.data,cfg.poster||{}),cv=$("poster"),btns=document.querySelectorAll("[data-needs]");poster=p;
  btns.forEach(function(b){b.disabled=!p.ok});
  if(!p.ok){cv.hidden=true;status(p.error,"err");return Promise.resolve(false)}
  if(!cfg.tpl){status("Poster designs could not be loaded. Check data/poster-templates.json.","err");return Promise.resolve(false)}
  var now=new Date();tpl=cfg.tpl.templates[todayIndex(now)];
  return Promise.all([fonts(),loadImg(tpl.image)]).then(function(a){var img=a[1];cv.hidden=false;cv.width=img.naturalWidth;cv.height=img.naturalHeight;
    draw(cv.getContext("2d"),cv.width,cv.height,img,tpl,cfg.tpl.layout,p,now);
    status(p.stale?"Rates are older than 24 hours – shown with their real update time. Tap Refresh Rates to retry.":"Poster ready – rates from "+p.source+".",p.stale?"warn":"ok");
    return true},
    function(e){status(e.message,"err");return false})}
function blob(){return render().then(function(ok){if(!ok)throw new Error("poster not ready");return new Promise(function(res,rej){$("poster").toBlob(function(b){b?res(b):rej(new Error("export failed"))},"image/png")})})}
function fname(){return "asian-jewellery-rates-"+C.dateLabel(new Date()).replace(/ /g,"-").toLowerCase()+".png"}
function download(b){var a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=fname();document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(a.href)},4000)}
function guard(fn){return function(){if(busy)return;busy=true;fn().catch(function(e){status("Could not create the poster: "+e.message,"err")}).then(function(){busy=false})}}
function share(){return blob().then(function(b){var f=new File([b],fname(),{type:"image/png"}),t=C.summary(poster,"Asian Jewellery");
  if(navigator.canShare&&navigator.canShare({files:[f]}))return navigator.share({files:[f],text:t}).then(function(){status("Shared. In WhatsApp choose Status to publish it.","ok")},function(e){if(e&&e.name!=="AbortError")throw e;status("Sharing cancelled.","")});
  download(b);status("Your poster is downloaded. This browser cannot send images directly – open WhatsApp, tap Status, and choose the downloaded image.","warn");
  window.open(C.waLink(PHONE,t),"_blank","noopener")})}
function copy(){var t=C.summary(poster,"Asian Jewellery");return (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){status("Rate summary copied.","ok")},function(){status("Copy is not available here – long-press the text instead.","warn")})}
function j(u){return fetch(u,{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json()}).catch(function(){return null})}
/* start immediately: templates + today's poster image download while rates are still being fetched */
var early=j("data/poster-templates.json").then(function(t){if(t&&t.templates){cfg.tpl=t;loadImg(t.templates[todayIndex(new Date())].image).catch(function(){})}return t});
document.addEventListener("DOMContentLoaded",function(){
  $("bGen").onclick=guard(function(){return render().then(function(ok){if(ok)status("Poster regenerated.","ok")})});
  $("bDown").onclick=guard(function(){return blob().then(function(b){download(b);status("Poster PNG downloaded.","ok")})});
  $("bShare").onclick=guard(share);$("bCopy").onclick=function(){if(poster&&poster.ok)copy()};
  $("bRef").onclick=function(){status("Refreshing rates…","");S.refresh(true).then(render)};
  Promise.all([j("data/poster-config.json"),early]).then(function(a){cfg.poster=a[0]||{};cfg.tpl=a[1];S.start(render)});
});
})();
