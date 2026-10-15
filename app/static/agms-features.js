/* AGMS dashboard enhancements: all optional; core app remains usable without this file. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const search=$('agmsSearch'), view=$('agmsView'), favorites=$('agmsFavorites'), tools=$('agmsTools');
if(!search||!view||!favorites||!tools)return;
const safeStore=(key,value)=>{try{localStorage.setItem(key,value)}catch{}};
const getStore=(key,fallback)=>{try{return localStorage.getItem(key)||fallback}catch{return fallback}};
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
const action=(label,fn)=>{const b=make('button',label,'agms-action');b.type='button';b.onclick=fn;return b};
const key=()=> 'agms-view-'+(workspace?.id||'');
view.value=getStore(key(),'tiles');
const origTile=tile,origRenderNav=renderNav,origShowHome=showHome,origShowGroup=showGroup,origOpenWorkspace=openWorkspace;
const statusCache=new Map();
function statusIndicator(item,container){
 if(!item.url||!workspace)return;
 const indicator=make('span','● Prüfe …','agms-status');container.append(indicator);
 const key=workspace.id+':'+item.id;
 function show(data){
  indicator.classList.remove('agms-online','agms-offline','agms-degraded');
  if(data.status==='online'){indicator.textContent='● Online';indicator.classList.add('agms-online')}
  else if(data.status==='degraded'){indicator.textContent='● Degraded';indicator.classList.add('agms-degraded')}
  else if(data.status==='offline'){indicator.textContent='● Offline';indicator.classList.add('agms-offline')}
  else{indicator.textContent='● Nicht prüfbar';indicator.title=data.reason==='private'?'Interne oder private Adressen werden aus Sicherheitsgründen nicht geprüft':'Der Status dieses Dienstes kann nicht ermittelt werden'}
 }
 const cached=statusCache.get(key);
 if(cached&&Date.now()-cached.time<60000){show(cached.data);return}
 fetch('/api/workspaces/'+encodeURIComponent(workspace.id)+'/status/'+encodeURIComponent(item.id),{credentials:'same-origin'})
 .then(async r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})
 .then(data=>{statusCache.set(key,{time:Date.now(),data});show(data)})
 .catch(()=>show({status:'unknown'}));
}

tile=function(item){
 const b=origTile(item);if(item.color)b.style.borderColor=item.color;
 if(item.color)b.style.setProperty('--agms-tile-color',item.color);
 const icon=b.querySelector('.web-tile-icon');if(icon){icon.style.color=item.color||'';if(item.icon_url&&/^https:\/\/[^\s]+$/i.test(item.icon_url)){const img=document.createElement('img');img.src=item.icon_url;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';img.className='agms-logo';img.onerror=()=>{img.remove();icon.textContent=item.icon||'◈'};icon.replaceChildren(img)}}
 if(item.favorite){const star=make('span','★','agms-tile-star');star.title='Favorit';b.append(star)}
 if(item.url)statusIndicator(item,b);
 return b;
};
function decorate(){
 if(!workspace)return;
 const query=search.value.trim().toLocaleLowerCase();
 const selected=selectedGroup;
 const base=selected?items.filter(n=>n.parent_id===selected):items.filter(n=>!n.parent_id);
 const matches=query?items.filter(n=>(n.title+' '+(n.url||'')).toLocaleLowerCase().includes(query)):base;
 const root=$('tiles');
 root.replaceChildren(...matches.map(tile));
 if(!matches.length)root.append(make('p',query?'Keine Treffer':'Noch keine Einträge vorhanden.'));
 root.classList.toggle('agms-list',view.value==='list');
 favorites.replaceChildren();
 if(!selected&&!query){
  const fav=items.filter(n=>n.favorite&&n.url);
  if(fav.length){favorites.append(make('h2','★ Favoriten'));const grid=make('div',undefined,'web-tiles');grid.classList.toggle('agms-list',view.value==='list');grid.append(...fav.map(tile));favorites.append(grid)}
 }
}
window.agmsRefreshHomeStatus=()=>{statusCache.clear();decorate()};
renderNav=function(){origRenderNav();for(const b of $('groupNav').children){const name=b.textContent.replace(/^▤\s*/, '');const item=items.find(n=>!n.url&&n.title===name);if(item?.color)b.style.borderLeft='3px solid '+item.color}};
showHome=function(){origShowHome();decorate()};
// Core UI bound this click handler before enhancements replaced showHome.
// Rebind so Overview renders the same favorites as the AGMS home entry.
$('showHome').onclick=()=>showHome();
showGroup=function(id){origShowGroup(id);decorate()};
openWorkspace=async function(id){await origOpenWorkspace(id);view.value=getStore(key(),'tiles');decorate()};
search.addEventListener('input',()=>{if(workspace)decorate()});
view.addEventListener('change',()=>{safeStore(key(),view.value);decorate()});
tools.append(action('Export JSON',()=>{
 if(!workspace)return;
 const data={format:'agms-navigation',version:1,homepage:workspace.name,items:items.map(n=>({...n}))};
 const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='agms-'+workspace.name.replace(/[^a-z0-9_-]/gi,'_')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}));
const file=document.createElement('input');file.type='file';file.accept='.json,application/json';file.hidden=true;tools.append(file);
tools.append(action('Import JSON',()=>{if(role==='viewer'){notify('Keine Bearbeitungsrechte');return}file.click()}));
file.addEventListener('change',async()=>{
 try{
  const chosen=file.files?.[0];if(!chosen)return;if(chosen.size>250000)throw Error('Datei zu groß');
  const data=JSON.parse(await chosen.text());
  if(data.format!=='agms-navigation'||data.version!==1||!Array.isArray(data.items)||data.items.length>150)throw Error('Ungültige AGMS-Exportdatei');
  const oldIds=new Set(),map=new Map();
  for(const n of data.items){
   if(!n||typeof n!=='object'||typeof n.title!=='string'||!n.title.trim()||n.title.length>80||typeof n.id!=='string'||oldIds.has(n.id))throw Error('Ungültiger Eintrag');
   oldIds.add(n.id);map.set(n.id,crypto.randomUUID());
  }
  const imported=data.items.map(n=>{
   const url=n.url||null;
   if(url){const u=new URL(url);if(!['http:','https:'].includes(u.protocol)||!u.hostname||u.username||u.password)throw Error('Ungültige URL')}
   if(n.parent_id&&!map.has(n.parent_id))throw Error('Unbekannte Gruppe');
   const color=/^#[0-9a-f]{6}$/i.test(n.color||'')?n.color:'';
   return {id:map.get(n.id),parent_id:n.parent_id?map.get(n.parent_id):null,title:n.title.trim(),icon:String(n.icon||'◈').slice(0,40),url,min_role:['viewer','editor','owner'].includes(n.min_role)?n.min_role:'viewer',open_mode:n.open_mode==='external'?'external':'embed',favorite:!!n.favorite,color,icon_url:typeof n.icon_url==='string'&&/^https:\/\/[^\s]+$/i.test(n.icon_url)?n.icon_url:''};
  });
  if(!confirm(imported.length+' Einträge importieren? Bestehende Einträge bleiben erhalten.'))return;
  if(items.length+imported.length>150)throw Error('Maximal 150 Einträge je Homepage');
  const combined=[...items,...imported];
  await api('/api/workspaces/'+workspace.id+'/navigation','PUT',{items:combined});
  await openWorkspace(workspace.id);notify(imported.length+' Einträge importiert');
 }catch(e){notify('Import fehlgeschlagen: '+e.message)}
 finally{file.value=''}
});
const dnd={id:null};
function enableDrag(){
 const root=$('tiles');
 root.addEventListener('dragstart',e=>{if(role==='viewer'||search.value)return;const b=e.target.closest('[data-agms-id]');if(!b)return;dnd.id=b.dataset.agmsId;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',dnd.id)});
 root.addEventListener('dragover',e=>{if(dnd.id)e.preventDefault()});
 root.addEventListener('drop',async e=>{
  e.preventDefault();const target=e.target.closest('[data-agms-id]');if(!target||!dnd.id||target.dataset.agmsId===dnd.id)return;
  const from=items.findIndex(n=>n.id===dnd.id),to=items.findIndex(n=>n.id===target.dataset.agmsId);
  if(from<0||to<0||items[from].parent_id!==items[to].parent_id)return;
  const backup=items.slice();const [moved]=items.splice(from,1);items.splice(items.findIndex(n=>n.id===target.dataset.agmsId),0,moved);
  try{await api('/api/workspaces/'+workspace.id+'/navigation','PUT',{items});renderNav();decorate();notify('Reihenfolge gespeichert')}catch(err){items=backup;decorate();notify(err.message)}
  dnd.id=null;
 });
 root.addEventListener('dragend',()=>{dnd.id=null});
}
const decoratedTile=tile;
tile=function(item){const b=decoratedTile(item);b.dataset.agmsId=item.id;b.draggable=role!=='viewer';return b};
enableDrag();
if(workspace)decorate();
})();
