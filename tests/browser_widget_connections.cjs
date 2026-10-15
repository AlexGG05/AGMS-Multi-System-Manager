const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8082');
 await page.locator('#username').fill('user@example.test');await page.locator('#password').fill('browser-test-password-long-enough');
 await page.getByRole('button',{name:'Sign in →',exact:true}).click();await page.locator('#showMonitoring').waitFor();
 await page.goto('http://localhost:8082/static/profile.html');
 for(const [title,label,token] of [['Proxmox widget connection','Proxmox API token','reader@pve!dashboard=test-secret'],['Arcane widget connection','Arcane API key','test-arcane-secret']]){
  const section=page.locator('.ops-section').filter({has:page.getByRole('heading',{name:title,exact:true})}).last();
  await section.getByLabel('Base URL',{exact:true}).fill('https://api.example:8006');await section.getByLabel(label,{exact:true}).fill(token);
  await section.getByRole('button',{name:'Save widget connection',exact:true}).click();
  await section.getByText('Configured. Leave credentials empty to keep the saved connection.',{exact:true}).waitFor();
  assert.equal(await section.getByLabel(label,{exact:true}).inputValue(),'');
 }
 await page.reload();
 const proxmox=page.locator('.ops-section').filter({has:page.getByRole('heading',{name:'Proxmox widget connection',exact:true})}).last();
 assert.equal(await proxmox.getByLabel('Base URL',{exact:true}).inputValue(),'https://api.example:8006');
 await proxmox.getByRole('button',{name:'Save widget connection',exact:true}).click();await page.getByText('Widget connection saved.',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});assert(await page.locator('main').evaluate(n=>n.scrollWidth<=n.clientWidth));
 await page.screenshot({path:'/tmp/agms-widget-connections-mobile.png',fullPage:true});
 await page.evaluate(()=>localStorage.setItem('agms-language','de'));await page.reload();
 await page.getByRole('heading',{name:'Proxmox-Widget-Verbindung',exact:true}).waitFor();await page.getByRole('heading',{name:'Arcane-Widget-Verbindung',exact:true}).waitFor();
 const arcane=page.locator('.ops-section').filter({has:page.getByRole('heading',{name:'Arcane-Widget-Verbindung',exact:true})}).last();
 await arcane.getByRole('button',{name:'Widget-Verbindung entfernen',exact:true}).click();await page.getByText('Widget-Verbindung entfernt.',{exact:true}).waitFor();
 assert.equal(await arcane.getByLabel('Basisadresse',{exact:true}).inputValue(),'');
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS Proxmox/Arcane profile connections, blank-key preservation, reload, removal, German and mobile');
})().catch(e=>{console.error(e);process.exit(1)});
