const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base='http://localhost:8082';
 await page.goto(base);await page.locator('.agms-footer').getByRole('link',{name:'Legal notice',exact:true}).click();
 await page.getByRole('heading',{name:'Legal notice',exact:true}).waitFor();assert.equal(new URL(page.url()).pathname,'/imprint');
 await page.locator('article:visible').getByText('Alexander Großkopf',{exact:false}).waitFor();
 assert.equal(await page.locator('article:visible a[href="mailto:info@agrosskopf.de"]').count(),1);
 await page.locator('#agmsLanguage').selectOption('de');await page.getByRole('heading',{name:'Impressum',exact:true}).waitFor();
 await page.locator('.agms-footer').getByRole('link',{name:'Datenschutzerklärung',exact:true}).click();
 await page.getByRole('heading',{name:'Datenschutzerklärung',exact:true}).waitFor();
 await page.getByRole('heading',{name:'5. Nutzung von AGMS',exact:true}).waitFor();
 assert.equal(await page.locator('article:visible').getByText('Hoste ich selber',{exact:true}).count(),0);
 assert.equal(await page.locator('article:visible').getByText('Inhaltsverzeichnis',{exact:true}).count(),0);
 await page.screenshot({path:'/tmp/agms-privacy-desktop.png'});
 await page.locator('#agmsLanguage').selectOption('en');await page.getByRole('heading',{name:'Privacy policy',exact:true}).waitFor();
 await page.getByRole('heading',{name:'5. Using AGMS',exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/agms-privacy-mobile.png'});
 for(const path of ['/impressum','/datenschutz','/static/signup.html','/static/forgot-password.html','/static/tickets.html']){
  const response=await page.goto(base+path);assert.equal(response.status(),200);
  assert.equal(await page.locator('.agms-footer a[href="/imprint"]').count(),1);
  assert.equal(await page.locator('.agms-footer a[href="/privacy"]').count(),1);
  assert.equal(await page.evaluate(()=>document.compatMode),'CSS1Compat');
 }
 await page.goto(base);await page.locator('#username').fill('user@example.test');await page.locator('#password').fill('browser-test-password-long-enough');await page.getByRole('button',{name:'Sign in →',exact:true}).click();await page.locator('#showMonitoring').waitFor();
 await page.locator('.agms-footer a[href="/privacy"]').click();await page.getByRole('heading',{name:'Privacy policy',exact:true}).waitFor();
 const nojs=await browser.newContext({javaScriptEnabled:false});const staticPage=await nojs.newPage();await staticPage.goto(base);await staticPage.locator('.agms-footer a[href="/imprint"]').click();await staticPage.getByRole('heading',{name:'Legal notice',exact:true}).waitFor();await staticPage.locator('.agms-footer a[href="/privacy"]').click();await staticPage.getByRole('heading',{name:'Privacy policy',exact:true}).waitFor();
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS public legal pages and aliases, footer before/after sign-in, source details, DE/EN, mobile, standards mode and no-JavaScript navigation');
})().catch(e=>{console.error(e);process.exit(1)});
