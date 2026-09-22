// Unmocked deployed API -> browser acceptance. Requires populated public collector.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const base=process.env.FRONTEND_URL||'https://trenchnet.app';
const s=await fetch(base+'/api/snapshot').then(r=>r.json());
assert.equal(s.analysis.version,'v2');assert.equal(s.analysis.paidModels,false);
assert.ok(s.traders.length);assert.ok(s.decisions.length);
const b=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try {
 const p=await b.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(base,{waitUntil:'domcontentloaded'});
 await p.locator('#content tbody tr').first().waitFor();
 await p.getByRole('button',{name:'Traders',exact:true}).click();
 await p.locator('#content .token-button').first().click();
 await p.locator('#detail .wallet-summary').waitFor();
 assert.match(await p.locator('#detail').innerText(),/OBSERVED SOL BOUGHT/);
 await p.locator('#close-detail').click();
 await p.getByRole('button',{name:'Network',exact:true}).click();
 await p.getByRole('heading',{name:'Repeated co-buy pairs',exact:true}).waitFor();
 const node=p.locator('.graph-node circle').first();await node.click();
 await p.locator('#detail .address').waitFor();await p.locator('#close-detail').click();
 await p.getByRole('button',{name:'Journal',exact:true}).click();
 await p.locator('.outcome').first().waitFor();
 assert.ok(await p.locator('.journal-entry a.receipt').count());
 await p.getByRole('button',{name:'Method',exact:true}).click();
 assert.match(await p.locator('#content').innerText(),/NO INFERENCE API/);
 await p.setViewportSize({width:390,height:844});
 for(const page of ['Traders','Network','Journal']) {
  await p.getByRole('button',{name:page,exact:true}).click();
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),page+' mobile overflow');
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'PASS',base,trades:s.trades.length,traders:s.traders.length,relationships:s.graph.relationships.length,journal:s.decisions.length,observedOutcomes:s.decisions.filter(d=>d.outcome.status==='observed').length}));
} finally {await b.close();}
