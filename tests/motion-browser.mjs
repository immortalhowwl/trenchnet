import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
try{
const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(process.env.FRONTEND_URL||'http://127.0.0.1:8879',{waitUntil:'networkidle'});
assert.equal(await page.locator('canvas.matrix-rain').count(),1,'Matrix rain canvas');
for(const width of [1440,1024,390,320]){
 await page.setViewportSize({width,height:950});await page.evaluate(()=>scrollTo(0,0));
 const pixels=await page.locator('.network-motion').evaluate(c=>c.toDataURL());
 const rainPixels=await page.locator('.matrix-rain').evaluate(c=>c.toDataURL());
 const a=await page.locator('.matrix-rain').getAttribute('data-frame');await page.waitForTimeout(400);const b=await page.locator('.matrix-rain').getAttribute('data-frame');assert.notEqual(a,b,'rain must advance');
 assert.notEqual(await page.locator('.network-motion').evaluate(c=>c.toDataURL()),pixels,'network pixels must move');
 assert.notEqual(await page.locator('.matrix-rain').evaluate(c=>c.toDataURL()),rainPixels,'rain pixels must move');
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow '+width);
 assert.ok(await page.locator('.network-motion').isVisible());
 if(process.env.MOTION_SCREENSHOTS)await page.screenshot({path:process.env.MOTION_SCREENSHOTS+'/motion-'+width+'.png'});
}
await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(100);const a=await page.locator('.matrix-rain').getAttribute('data-frame');await page.waitForTimeout(250);assert.equal(await page.locator('.matrix-rain').getAttribute('data-frame'),a);
await page.emulateMedia({reducedMotion:'no-preference'});await page.locator('#workspace').scrollIntoViewIfNeeded();await page.evaluate(()=>scrollTo(0,document.body.scrollHeight));await page.waitForTimeout(250);const c=await page.locator('.matrix-rain').getAttribute('data-frame');await page.waitForTimeout(250);assert.equal(await page.locator('.matrix-rain').getAttribute('data-frame'),c,'offscreen pause');
assert.deepEqual(errors,[]);console.log('PASS matrix rain and network animation, 4 viewport sizes, reduced-motion, offscreen pause, no JS errors');
}finally{await browser.close();}
