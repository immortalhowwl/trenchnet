// Explicit API fixtures exercise v2 rendering; live-server smoke follows separately.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined});
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const wallet='11111111111111111111111111111111',other='22222222222222222222222222222222',mint='33333333333333333333333333333333';
const trade={id:'receipt-1',wallet,mint,side:'buy',timestamp:'2026-09-22T10:00:00Z',solAmount:2,explorerUrl:'https://solscan.io/tx/example'};
const profile={address:wallet,buys:1,sells:0,tokens:1,firstSeen:trade.timestamp,lastSeen:trade.timestamp,observedSolBought:2,observedSolSold:0,summary:'Retained sample only <img src=x onerror=alert(1)>'};
const snapshot={markets:[],trades:[trade],traders:[profile],decisions:[{mint,kind:'shared_buys',summary:'Observed shared asset',rulesVersion:'v2',timestamp:trade.timestamp,evidence:['receipt-1'],outcome:{status:'observed',summary:'Later activity in retained sample',buys:2,sells:1,wallets:2,evidence:['receipt-1']}},{mint,kind:'first_seen',summary:'First observation',rulesVersion:'v2',timestamp:trade.timestamp,outcome:{status:'pending'}}],graph:{nodes:[],edges:[],relationships:[{wallets:[wallet,other],sharedTokens:[mint],sharedTokenCount:1,evidence:['receipt-1']}]},status:{collector:'ok',analysis:{engine:'rules',version:'v2',paidModels:false}}};
try{
 await page.route('**/api/**',route=>{const url=new URL(route.request().url());return route.fulfill({json:url.pathname==='/api/wallet'?{profile,trades:[trade],decisions:[]}:url.pathname==='/api/token'?{trades:[trade],decisions:[]}:snapshot});});
 await page.goto(process.env.FRONTEND_URL||'http://127.0.0.1:8765');
 await page.getByRole('button',{name:'Method',exact:true}).click();
 assert.match(await page.locator('#content').innerText(),/deterministic on-chain rules/i);
 assert.doesNotMatch(await page.locator('body').innerText(),/ASTRA|JEV|NOT CONNECTED/);
 await page.getByRole('button',{name:'Network',exact:true}).click();
 await page.getByRole('heading',{name:'Repeated co-buy pairs'}).waitFor();
 assert.match(await page.locator('#content').innerText(),/shared asset.*human coordination/i);
 await page.locator('.relationship-entry button').first().click();
 await page.getByText(profile.summary,{exact:true}).waitFor();
 assert.equal(await page.locator('#detail-content img').count(),0);
 for(const label of ['FIRST SEEN','LAST SEEN','OBSERVED SOL BOUGHT','OBSERVED SOL SOLD'])assert.match(await page.locator('#detail-content').innerText(),new RegExp(label));
 assert.doesNotMatch(await page.locator('#detail-content').innerText(),/PNL/i);
 await page.getByRole('button',{name:'Close details'}).click();
 await page.locator('.relationship-entry .actions').nth(1).getByRole('button').click();await page.getByRole('heading',{name:'Token dossier'}).waitFor();await page.getByRole('button',{name:'Close details'}).click();
 await page.getByRole('button',{name:'Journal',exact:true}).click();
 assert.equal(await page.getByText('What happened next · 1h observed window',{exact:true}).count(),2);
 assert.match(await page.locator('#content').innerText(),/No observed later records/);
 assert.equal(await page.locator('.outcome a').count(),1);
 snapshot.trades[0].explorerUrl='javascript:alert(1)';await page.getByRole('button',{name:'Refresh ↻'}).click();await page.getByText('Receipt unavailable').first().waitFor();assert.equal(await page.locator('#content a[href^="javascript:"]').count(),0);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 snapshot.decisions[0].outcome.evidence=['missing'];snapshot.graph.relationships=[];
 await page.getByRole('button',{name:'Refresh ↻'}).click();await page.getByText('Evidence outside snapshot: missi…sing').waitFor();
 await page.getByRole('button',{name:'Network',exact:true}).click();await page.getByText('No repeated co-buy pairs observed').waitFor();
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.deepEqual(errors,[]);console.log('PASS v2: rules method, relationship navigation/empty state, wallet sample metrics/XSS, outcomes/pending/evidence, mobile');
}finally{await browser.close();}
