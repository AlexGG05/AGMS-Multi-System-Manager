const $=id=>document.getElementById(id);
const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )csrf=([^;]*)/)||[])[1]||'');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,method='GET',body){const r=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'HTTP '+r.status);return d}
let restoringWebUi=false;
let workspaces=[],workspace=null,items=[],role='viewer',tier=0,selectedGroup=null,editing=false,workspaceLocked=false;
const notify=message=>$('notice').textContent=message;
function panels(id){if(id!=='framePanel'){setFrameExpanded(false);if(!restoringWebUi&&location.pathname.startsWith('/webui/'))history.replaceState(null,'','/');}$('showMonitoring').classList.toggle('active',id==='monitoringPanel');$('showHome').classList.toggle('active',id==='homePanel');$('showStatus').classList.toggle('active',id==='statusPanel');for(const key of ['homePanel','framePanel','editorPanel','teamPanel','statusPanel','monitoringPanel'])$(key).hidden=key!==id}
function maxHomes(){return tier===3?10:tier===2?5:tier===1?3:1}
async function init(){const route=location.pathname.match(/^\/webui\/([^/]+)\/([^/]+)\/$/);restoringWebUi=true;try{const data=await api('/api/workspaces');workspaces=data.workspaces;tier=data.tier;$('tierLabel').textContent=data.account_role==='admin'?'Administrator':tier?'Tier '+tier:'Free · 1 Homepage';$('premiumLink').hidden=data.account_role!=='admin';$('workspaceSelect').replaceChildren(...workspaces.map(w=>{const option=document.createElement('option');option.value=w.id;option.textContent=w.name;return option}));if(!workspaces.length){notify('Erstelle deine erste Homepage.');panels('homePanel');return}const stored=localStorage.getItem('codex-active-homepage');await openWorkspace((route&&workspaces.find(w=>w.id===decodeURIComponent(route[1]))?.id)||workspaces.find(w=>w.id===stored)?.id||workspaces[0].id);restoringWebUi=false;if(route){const item=items.find(n=>n.id===decodeURIComponent(route[2])&&n.url);if(item){selectedGroup=item.parent_id||null;openFrame(item)}else{notify('WebUI not found');history.replaceState(null,'','/')}}await showNotifications();loadProfileBadge()}catch(e){notify(e.message)}finally{restoringWebUi=false;$('showMonitoring').disabled=false;$('showStatus').disabled=false;$('notificationBell').disabled=false}}
async function loadProfileBadge(){try{const p=await api('/api/account/profile');$('profileName').textContent=p.display_name||'Profil';if(p.avatar)$('profileAvatar').src=p.avatar}catch(e){console.warn('Profil konnte nicht geladen werden',e)}}
async function openWorkspace(id){try{const d=await api('/api/workspaces/'+id);workspace=d.workspace;role=d.role;workspaceLocked=d.editable===false;items=d.navigation;editing=false;selectedGroup=null;localStorage.setItem('codex-active-homepage',id);$('workspaceSelect').value=id;$('pageTitle').textContent=workspace.name;$('deleteWorkspace').disabled=role!=='owner';$('renameWorkspace').disabled=role!=='owner'||workspaceLocked;$('editButton').hidden=role==='viewer'||workspaceLocked;$('addGroup').hidden=role==='viewer'||workspaceLocked;$('addWebui').hidden=role==='viewer'||workspaceLocked;$('invite').hidden=role!=='owner'||workspaceLocked;notify(workspaceLocked?'Nur Lesen: Diese Homepage liegt über dem Limit deines aktuellen Tiers. Die Inhalte bleiben verfügbar.':'');renderNav();showHome()}catch(e){notify(e.message)}}
let frameOriginalParent=null,frameOriginalNext=null;
function setFrameExpanded(expanded){if(typeof window.agmsSetFrameMode==='function'){window.agmsSetFrameMode(expanded);return;}
 const panel=$('framePanel'),button=$('expandFrame');
 if(expanded){
  if(panel.classList.contains('web-frame-expanded'))return;
  frameOriginalParent=panel.parentNode;frameOriginalNext=panel.nextSibling;
  document.body.appendChild(panel);
  panel.classList.add('web-frame-expanded');
  panel.style.cssText='position:fixed!important;inset:0!important;z-index:2147483647!important;display:flex!important;flex-direction:column!important;width:100vw!important;height:100dvh!important;max-height:100dvh!important;margin:0!important;padding:env(safe-area-inset-top) 8px env(safe-area-inset-bottom)!important;box-sizing:border-box!important;overflow:hidden!important;background:#0b1220!important';
  document.body.style.overflow='hidden';
 }else{
  panel.classList.remove('web-frame-expanded');panel.style.removeProperty('position');panel.removeAttribute('style');
  if(frameOriginalParent){frameOriginalParent.insertBefore(panel,frameOriginalNext&&frameOriginalNext.parentNode===frameOriginalParent?frameOriginalNext:null);frameOriginalParent=null;frameOriginalNext=null}
  document.body.style.overflow='';
 }
 button.textContent=expanded?'⤢ Verkleinern':'⛶ Vollbild';button.setAttribute('aria-pressed',String(expanded));
}
function renderNav(){$('groupNav').replaceChildren();for(const group of items.filter(n=>!n.url)){const b=document.createElement('button');b.className='web-nav';b.textContent='▤  '+group.title;b.onclick=()=>showGroup(group.id);$('groupNav').append(b)}}
function tile(item){const b=document.createElement('button');b.className='web-tile';const icon=document.createElement('span');icon.className='web-tile-icon';icon.textContent=item.icon||'◈';const name=document.createElement('strong');name.textContent=item.title;const sub=document.createElement('small');sub.textContent=item.url?'Weboberfläche':'Gruppe öffnen';b.append(icon,name,sub);b.onclick=()=>item.url?openFrame(item):showGroup(item.id);return b}
function showHome(){selectedGroup=null;$('breadcrumb').textContent='ÜBERSICHT';$('pageTitle').textContent=workspace?.name||'Meine Homepage';$('tiles').replaceChildren(...items.filter(n=>!n.parent_id).map(tile));if(!$('tiles').children.length){const p=document.createElement('p');p.textContent='Noch keine Weboberflächen. Über „WebUI hinzufügen“ kannst du deinen ersten Dienst anlegen.';$('tiles').append(p)}panels('homePanel')}
function showGroup(id){selectedGroup=id;const group=items.find(n=>n.id===id&&!n.url);if(!group)return showHome();$('breadcrumb').textContent=workspace.name;$('pageTitle').textContent=group.title;$('tiles').replaceChildren(...items.filter(n=>n.parent_id===id).map(tile));panels('homePanel')}
function openFrame(item){
 if(!item.url)return;
 if(item.open_mode==='external'){window.open(item.url,'_blank','noopener,noreferrer');return}
 try{
  const u=new URL(item.url);
  if(!['http:','https:'].includes(u.protocol))throw Error('URL');
  if(item.open_mode==='proxy'&&(u.protocol!=='https:'||u.username||u.password||u.hash)){notify('Proxy requires an HTTPS URL without credentials or a fragment');return}
  const route='/webui/'+encodeURIComponent(workspace.id)+'/'+encodeURIComponent(item.id)+'/';
  // A real navigation makes the extension re-evaluate this service's tab URL.
  if(location.pathname!==route){location.assign(route);return}
  $('webFrame').src=item.open_mode==='proxy'?'/web-proxy/'+encodeURIComponent(workspace.id)+'/'+encodeURIComponent(item.id)+u.pathname+u.search:u.href;
  $('external').href=u.href;$('frameTitle').textContent=item.title;$('breadcrumb').textContent=workspace.name+(item.open_mode==='proxy'?' / PROXY':' / WEBUI');$('pageTitle').textContent=item.title;panels('framePanel');
 }catch{notify('Ungültige WebUI-Adresse')}
}
$('passwordManagerSetup').onclick=()=>window.agmsPasswordManagerSetup({website:$('external').href,tab:location.href,frame:$('webFrame').src});
function edit(){if(role==='viewer'||workspaceLocked)return;editing=true;panels('editorPanel');drawEditor()}
function drawEditor(){
 const root=$('editorItems');root.replaceChildren();
 const groups=items.filter(n=>!n.url);
 const heading=document.createElement('h3');heading.textContent=selectedGroup?'Gruppe verwalten: '+(groups.find(g=>g.id===selectedGroup)?.title||'Gruppe'):'Homepage verwalten';root.append(heading);
 const helper=document.createElement('p');helper.textContent=selectedGroup?'Hier kannst du diese Gruppe und ihre WebUIs bearbeiten.':'Wähle eine Gruppe aus oder erstelle eine neue. WebUIs werden innerhalb der jeweiligen Gruppe verwaltet.';root.append(helper);
 function action(label,callback){const b=document.createElement('button');b.type='button';b.className='web-editor-action';b.textContent=label;b.onclick=callback;return b}
 function field(label,value,onchange,type='text'){const wrap=document.createElement('label');wrap.className='web-config-field';const cap=document.createElement('span');cap.textContent=label;const input=document.createElement('input');input.type=type;input.value=value||'';input.oninput=()=>onchange(input.value);wrap.append(cap,input);return wrap}
 function rowFor(item){
  const card=document.createElement('div');card.className='web-config-card';
  const header=document.createElement('strong');header.textContent=item.url?'◈ '+item.title:'▤ '+item.title;card.append(header);
  card.append(field('Name',item.title,v=>item.title=v));
  card.append(field('Icon: Emoji oder HTTPS-Bildadresse',item.icon_url||item.icon||'◈',v=>{const value=v.trim();if(/^https?:\/\//i.test(value)){item.icon_url=value}else{item.icon=value;item.icon_url=''};}));
  const help=document.createElement('small');help.textContent='Beispiel: 🖥️ oder https://example.com/logo.png (auch SVG/WebP).';help.className='web-hint';card.append(help);
  const colorLabel=document.createElement('label');colorLabel.className='web-config-field';colorLabel.textContent='Kachelfarbe';const colorInput=document.createElement('input');colorInput.type='color';colorInput.value=/^#[0-9a-f]{6}$/i.test(item.color||'')?item.color:'#243b5a';colorInput.oninput=()=>item.color=colorInput.value;colorLabel.append(colorInput);card.append(colorLabel);
  const favoriteLabel=document.createElement('label');favoriteLabel.className='web-config-check';const favoriteInput=document.createElement('input');favoriteInput.type='checkbox';favoriteInput.checked=!!item.favorite;favoriteInput.onchange=()=>item.favorite=favoriteInput.checked;favoriteLabel.append(favoriteInput,document.createTextNode(' Als Favorit anzeigen'));card.append(favoriteLabel);
  if(item.url){
   card.append(field('WebUI-Adresse',item.url,v=>item.url=v,'url'));
   const label=document.createElement('label');label.className='web-config-field';const cap=document.createElement('span');cap.textContent='Öffnungsmodus';const select=document.createElement('select');
   [['embed','Innerhalb von AGMS (iframe)'],['external','Extern in neuem Tab'],['proxy','Über AGMS-Proxy öffnen (Freigabe durch Administrator)']].forEach(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o)});
   select.value=item.open_mode||'embed';select.onchange=()=>item.open_mode=select.value;label.append(cap,select);card.append(label);
  }
  const actions=document.createElement('div');actions.className='web-config-actions';
  for(const [direction,label] of [[-1,'↑'],[1,'↓']])actions.append(action(label,()=>{const siblings=items.filter(n=>n.parent_id===item.parent_id);const at=siblings.findIndex(n=>n.id===item.id);const target=siblings[at+direction];if(!target)return;const from=items.indexOf(item),to=items.indexOf(target);[items[from],items[to]]=[items[to],items[from]];drawEditor()}));
  actions.append(action('Löschen',()=>{if(!confirm('„'+item.title+'“ wirklich löschen?'+(!item.url?' Alle WebUIs dieser Gruppe werden ebenfalls entfernt.':'')))return;items=items.filter(n=>n.id!==item.id&&n.parent_id!==item.id);if(selectedGroup===item.id)selectedGroup=null;drawEditor()}));
  if(item.url)actions.prepend(action('Duplizieren',()=>{items.push({...item,id:crypto.randomUUID(),title:item.title+' (Kopie)'});drawEditor()}));
  card.append(actions);return card;
 }
 if(selectedGroup){
  root.append(action('Gruppe duplizieren',()=>{const original=groups.find(g=>g.id===selectedGroup);if(!original)return;const copyId=crypto.randomUUID();items.push({...original,id:copyId,title:original.title+' (Kopie)'});for(const child of items.filter(n=>n.parent_id===original.id))items.push({...child,id:crypto.randomUUID(),parent_id:copyId});selectedGroup=copyId;drawEditor()}));
  const group=groups.find(g=>g.id===selectedGroup);
  if(group)root.append(rowFor(group));
  const subtitle=document.createElement('h3');subtitle.textContent='WebUIs in dieser Gruppe';root.append(subtitle);
  root.append(action('＋ WebUI in dieser Gruppe',()=>addItem(false)));
  for(const item of items.filter(n=>n.url&&n.parent_id===selectedGroup))root.append(rowFor(item));
  root.append(action('← Alle Gruppen',()=>{selectedGroup=null;drawEditor()}));
 }else{
  root.append(action('＋ Neue Gruppe',()=>addItem(true)));
  for(const group of groups){
   const line=document.createElement('div');line.className='web-group-config';
   const name=document.createElement('strong');name.textContent='▤ '+group.title;
   const count=document.createElement('span');count.textContent=items.filter(n=>n.parent_id===group.id).length+' WebUIs';
   line.append(name,count,action('Verwalten →',()=>{selectedGroup=group.id;drawEditor()}),action('↑',()=>{const index=items.indexOf(group);const previous=items.slice(0,index).reverse().find(n=>!n.url);if(previous){const at=items.indexOf(previous);[items[at],items[index]]=[items[index],items[at]];drawEditor()}}),action('↓',()=>{const index=items.indexOf(group);const next=items.slice(index+1).find(n=>!n.url);if(next){const at=items.indexOf(next);[items[at],items[index]]=[items[index],items[at]];drawEditor()}}));root.append(line);
  }
  const ungrouped=items.filter(n=>n.url&&!n.parent_id);
  if(ungrouped.length){const h=document.createElement('h3');h.textContent='Ohne Gruppe';root.append(h);for(const item of ungrouped)root.append(rowFor(item))}
  root.append(action('＋ WebUI ohne Gruppe',()=>addItem(false)));
 }
}
function addItem(group){
 if(role==='viewer'||workspaceLocked)return;
 if(!editing){editing=true;panels('editorPanel')}
 const name=prompt(group?'Name der neuen Gruppe':'Name der neuen WebUI');
 if(!name?.trim())return;
 let url=null,open_mode='embed';
 if(!group){
  url=prompt('WebUI-Adresse (https:// oder http://)');
  if(!url)return;
  try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol)||!u.hostname||u.username||u.password)throw Error('URL')}catch{return notify('Bitte eine gültige HTTP(S)-Adresse eingeben')}
  open_mode=confirm('WebUI extern in einem neuen Tab öffnen?\nOK = Extern öffnen\nAbbrechen = In AGMS einbetten')?'external':'embed';
 }
 const id=crypto.randomUUID();
 items.push({id,title:name.trim(),url,icon:group?'▤':'◈',parent_id:group?null:selectedGroup,min_role:'viewer',open_mode});
 if(group)selectedGroup=id;
 drawEditor();
}
async function save(){
 if(workspaceLocked)return notify('Diese Homepage ist schreibgeschützt.');
 try{
  await api('/api/workspaces/'+workspace.id+'/navigation','PUT',{items});
  const returnGroup=selectedGroup;
  await openWorkspace(workspace.id);
  if(returnGroup&&items.some(n=>n.id===returnGroup&&!n.url))showGroup(returnGroup);
  notify('Änderungen gespeichert');
 }catch(e){notify('Speichern fehlgeschlagen: '+e.message)}
}
async function team(){try{const data=await api('/api/workspaces/'+workspace.id+'/members');$('members').replaceChildren();for(const m of data.members){const row=document.createElement('div');row.className='web-member';const text=document.createElement('span');text.textContent=(m.email||m.username)+' · '+m.role;row.append(text);if(role==='owner'&&m.role!=='owner'){const remove=document.createElement('button');remove.textContent='Entfernen';remove.onclick=async()=>{if(!confirm('Teammitglied entfernen?'))return;try{await api('/api/workspaces/'+workspace.id+'/members/'+encodeURIComponent(m.username),'DELETE');await team()}catch(e){notify(e.message)}};row.append(remove)}$('members').append(row)}panels('teamPanel')}catch(e){notify(e.message)}}
async function showNotifications(){try{const data=await api('/api/notifications');const root=$('notifications');root.replaceChildren();$('notificationCount').textContent=String(data.notifications.length);$('notificationCount').hidden=!data.notifications.length;if(!data.notifications.length){const empty=document.createElement('p');empty.className='web-empty';empty.textContent='Keine neuen Benachrichtigungen';root.append(empty)}for(const n of data.notifications){const box=document.createElement('div');box.className='web-member';const label=document.createElement('span');if(n.ticket_id){const title=document.createElement('strong');title.textContent=n.message;const summary=document.createElement('p');summary.textContent='#'+n.ticket_number+' · '+(n.ticket_subject||'');summary.dataset.agmsI18nIgnore='';label.append(title,summary);if(n.ticket_comment){const comment=document.createElement('p');comment.textContent=n.ticket_comment;comment.dataset.agmsI18nIgnore='';comment.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';label.append(comment)}}else if(n.message.startsWith('Expiry warning: ')){const title=document.createElement('strong');title.textContent='Expiry warning';const context=document.createElement('p');context.textContent=n.message.slice(16);context.dataset.agmsI18nIgnore='';label.append(title,context)}else{label.textContent='🔔 '+n.message;}const open=document.createElement('button');open.textContent='Öffnen';open.onclick=async()=>{if(n.ticket_id){await api('/api/notifications/'+n.id+'/read','POST');window.location.href='/static/tickets.html?ticket='+encodeURIComponent(n.ticket_id);return}if(n.message.startsWith('Expiry warning: ')){await api('/api/notifications/'+n.id+'/read','POST');$('showMonitoring').click();return}if(n.message.startsWith('Neue Proxy-Freigabe angefragt:')){await api('/api/notifications/'+n.id+'/read','POST');window.location.href='/static/admin-panel.html#proxy-requests';return}await api('/api/notifications/'+n.id+'/read','POST');await init();if(workspaces.some(w=>w.id===n.workspace_id))await openWorkspace(n.workspace_id);await showNotifications()};const dismiss=document.createElement('button');dismiss.textContent='×';dismiss.onclick=async()=>{await api('/api/notifications/'+n.id+'/read','POST');await showNotifications()};box.append(label,open,dismiss);root.append(box)}}catch(e){notify(e.message)}}
$('renameWorkspace').onclick=async()=>{if(!workspace){notify('Bitte zuerst eine Homepage auswählen');return}if(role!=='owner'){notify('Nur der Besitzer kann diese Homepage umbenennen');return}const name=window.prompt('Neuer Name der Homepage:',workspace.name);if(name===null)return;const cleaned=name.trim();if(!cleaned||cleaned.length>80){notify('Der Name muss zwischen 1 und 80 Zeichen enthalten');return}if(cleaned===workspace.name)return;try{const result=await api('/api/workspaces/'+encodeURIComponent(workspace.id),'PATCH',{name:cleaned});workspace.name=result.name||cleaned;for(const w of workspaces){if(w.id===workspace.id)w.name=workspace.name}const option=Array.from($('workspaceSelect').options).find(o=>o.value===workspace.id);if(option)option.textContent=workspace.name;$('pageTitle').textContent=workspace.name;notify('Homepage erfolgreich umbenannt')}catch(e){notify('Umbenennen fehlgeschlagen: '+e.message);window.alert('Umbenennen fehlgeschlagen: '+e.message)}};

$('notificationBell').onclick=()=>{const menu=$('notificationMenu');menu.hidden=!menu.hidden;$('notificationBell').setAttribute('aria-expanded',String(!menu.hidden));if(!menu.hidden)showNotifications()};
$('closeNotifications').onclick=()=>{$('notificationMenu').hidden=true;$('notificationBell').setAttribute('aria-expanded','false')};
$('workspaceSelect').onchange=e=>openWorkspace(e.target.value);
$('showHome').onclick=showHome;$('back').onclick=()=>selectedGroup?showGroup(selectedGroup):showHome();
$('reload').onclick=()=>{const f=$('webFrame');f.src=f.src};
// Fullscreen button uses a self-contained inline handler for mobile Safari reliability.
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('framePanel').classList.contains('web-frame-expanded'))setFrameExpanded(false)});
$('addGroup').onclick=()=>{selectedGroup=null;addItem(true)};$('addWebui').onclick=()=>addItem(false);
$('editButton').onclick=edit;
$('saveNavigation').onclick=save;$('cancelEdit').onclick=()=>openWorkspace(workspace.id);
$('addWorkspace').onclick=async()=>{const name=prompt('Name der neuen Homepage');if(!name?.trim())return;try{const data=await api('/api/workspaces','POST',{name:name.trim()});await init();await openWorkspace(data.id)}catch(e){notify(e.message)}};
$('deleteWorkspace').onclick=async()=>{if(!workspace||role!=='owner')return;if(!confirm('Homepage „'+workspace.name+'“ mit allen Gruppen, Widgets und Teamzuordnungen endgültig löschen?'))return;try{await api('/api/workspaces/'+workspace.id,'DELETE');localStorage.removeItem('codex-active-homepage');workspace=null;await init();notify('Homepage gelöscht')}catch(e){notify(e.message)}};
$('teamButton').onclick=team;$('closeTeam').onclick=showHome;
$('invite').onclick=async()=>{const email=prompt('E-Mail-Adresse des Teammitglieds');if(!email)return;const role=prompt('Rolle: viewer oder editor','viewer');try{await api('/api/workspaces/'+workspace.id+'/invitations','POST',{email,role});notify('Benutzer hinzugefügt oder per E-Mail eingeladen')}catch(e){notify(e.message)}};
$('logout').onclick=async()=>{try{await api('/api/logout','POST');location.href='/'}catch(e){notify(e.message)}};
init();

setInterval(showNotifications,30000);
window.addEventListener('agms-ticket-updated',showNotifications);

$('showStatus').onclick=()=>{panels('statusPanel');$('breadcrumb').textContent='STATUS';$('pageTitle').textContent='Status overview';window.agmsShowStatus()};
$('reportServiceIssue').onclick=()=>{const route=location.pathname.match(/^\/webui\/([^/]+)\/([^/]+)\/$/);if(route)window.agmsCreateTicket({workspace_id:decodeURIComponent(route[1]),service_id:decodeURIComponent(route[2])}).catch(e=>notify(e.message))};
window.agmsOpenSearchGroup=async(wsid,id)=>{$('agmsSearch').value='';await openWorkspace(wsid);showGroup(id)};
window.addEventListener('agms-notification-settings-updated',showNotifications);

$('showMonitoring').onclick=()=>{panels('monitoringPanel');$('pageTitle').textContent='Monitoring';$('breadcrumb').textContent='MONITORING';window.agmsShowMonitoring?.()};
