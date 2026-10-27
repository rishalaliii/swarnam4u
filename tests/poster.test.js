const assert=require("assert"),C=require("../assets/poster-core.js"),fs=require("fs");
const data=JSON.parse(fs.readFileSync(__dirname+"/../data/rates.json","utf8"));
const p=C.build(data,{});assert(p.ok);const by=k=>p.rows.find(r=>r.k===k);
const gold22=Number(data.gold["22K · 916"].today),gold18=Number(data.gold["18K · 750"].today),silver=Number(data.silver["Silver · 999"].today);
assert.deepStrictEqual(by("22K").v,[gold22,gold22*8]);        // pawan = 8 g
assert.deepStrictEqual(by("18K").v,[gold18,gold18*8]);
assert.deepStrictEqual(by("SILVER").v,[silver,silver*10]);    // 10 g
assert.strictEqual(by("14K").v[0],Math.round((gold22*585/916)/10)*10);
assert.strictEqual(by("14K").src,"calculated");
assert.strictEqual(C.build(data,{overrides:{"14K":8570}}).rows[2].v[1],68560);
assert(!C.build({},{}).ok);assert(!C.build({updated:"2026-10-21T11:30:00+05:30",gold:{},silver:{}},{}).ok);
assert.strictEqual(C.inr(107120),"₹ 1,07,120");
assert.strictEqual(C.dateLabel(new Date("2026-10-21T23:50:00Z")),"22 OCT 2026");  // IST rollover
assert.strictEqual(C.dayLabel(new Date("2026-10-21T06:00:00Z")),"WEDNESDAY");
assert.strictEqual(C.timeLabel(new Date("2026-10-21T06:00:00Z")),"11:30 AM IST");
assert.strictEqual(C.waLink("98952 32441"),"https://wa.me/919895232441");
assert.strictEqual(C.waLink("98952 32441","Hello world"),"https://wa.me/919895232441?text=Hello%20world");
assert(C.build(Object.assign({},data,{updated:"2026-10-01T10:00:00+05:30"}),{}).stale);
const T=JSON.parse(fs.readFileSync(__dirname+"/../data/poster-templates.json","utf8"));
assert.strictEqual(T.templates.length,10);T.templates.forEach(t=>assert(fs.existsSync(__dirname+"/../"+t.image),t.image));
const pick=d=>C.pickIndex(new Date(d+"T12:00:00+05:30"),T.anchorDate,10)+1;
assert.deepStrictEqual(["2026-10-21","2026-10-22","2026-10-30","2026-10-31","2026-11-01"].map(pick),[1,2,10,1,2]);
assert.strictEqual(pick("2026-10-20"),10);                                              // before anchor still wraps correctly
assert.strictEqual(C.pickIndex(new Date("2026-10-21T18:45:00Z"),T.anchorDate,10),1);   // 00:15 IST on 22 Oct -> Design 2
assert.strictEqual(C.pickIndex(new Date("2026-10-21T18:29:00Z"),T.anchorDate,10),0);   // 23:59 IST on 21 Oct -> Design 1
console.log("all poster tests passed");
