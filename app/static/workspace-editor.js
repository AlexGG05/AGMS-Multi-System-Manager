/* Explicit homepage editing. Connection drafts and secrets live only in memory. */
(()=>{'use strict';
let snapshot=null,groupAtStart=null,dirty=false;
const pending=new Map();
window.agmsLayoutEditing=false;
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e};
function button(text,label,fn){const b=make('button',text,'layout-control');b.type='button';b.setAttribute('aria-label',label);b.title=label;b.onclick=e=>{e.stopPropagation();fn()};return b}
const bar=make('div',undefined,'workspace-editbar');bar.hidden=true;
const message=make('span','Edit mode: use the pencil on a tile or group.');
const done=button('Done','Save layout',()=>finish());
const cancel=button('Cancel','Discard layout changes',()=>discard());
const groupEdit=button('✎','Edit group',()=>editEntry(items.find(n=>n.id===selectedGroup)));
bar.append(message,groupEdit,button('＋ Add group','Add group',()=>editEntry(null,'group')),button('＋ Add WebUI','Add WebUI',()=>editEntry(null,'embed')),done,cancel);
$('homePanel').prepend(bar);
function allowed(){return workspace&&role!=='viewer'&&!workspaceLocked}
function controls(){
 const on=!!window.agmsLayoutEditing;bar.hidden=!on;groupEdit.hidden=!on||!selectedGroup;
 $('editButton').textContent=on?'Done':'Bearbeiten';$('editButton').setAttribute('aria-pressed',String(on));
 // Creation belongs to the edit toolbar, never to normal browsing.
 for(const id of ['addGroup','addWebui'])$(id).hidden=true;
 $('renameWorkspace').disabled=!on||role!=='owner'||workspaceLocked;$('deleteWorkspace').disabled=!on||role!=='owner';
 document.body.classList.toggle('homepage-editing',on);
}
function redraw(){renderNav();if(selectedGroup)showGroup(selectedGroup);else showHome();controls()}
function begin(){if(!allowed())return;snapshot=JSON.parse(JSON.stringify(items));groupAtStart=selectedGroup;pending.clear();window.agmsLayoutEditing=true;dirty=false;notify('');redraw()}
window.agmsBeginLayoutEdit=begin;
async function finish(){
 if(!window.agmsLayoutEditing||!allowed())return false;
 done.disabled=true;$('editButton').disabled=true;
 try{
  await api('/api/workspaces/'+workspace.id+'/navigation','PUT',{items});
  snapshot=JSON.parse(JSON.stringify(items));
  // Each secret is submitted only after its tile exists; never export it as navigation.
  for(const [id,config] of pending){await api('/api/workspaces/'+workspace.id+'/remote/'+id,config===null?'DELETE':'PUT',config===null?undefined:config);pending.delete(id)}
  window.agmsLayoutEditing=false;snapshot=null;dirty=false;editing=false;
  const group=selectedGroup;await openWorkspace(workspace.id);if(group)showGroup(group);notify('Layout saved.');return true;
 }catch(e){notify(pending.size?'Layout save or connection setup failed. Review the connection and try Done again. '+e.message:e.message);return false}
 finally{done.disabled=false;$('editButton').disabled=false;controls()}
}
function discard(){if(!window.agmsLayoutEditing)return;items=snapshot||items;selectedGroup=groupAtStart;window.agmsLayoutEditing=false;snapshot=null;pending.clear();dirty=false;editing=false;redraw()}
$('editButton').onclick=()=>window.agmsLayoutEditing?finish():begin();
const originalOpenWorkspace=openWorkspace;
openWorkspace=async function(id){
 if(window.agmsLayoutEditing&&dirty&&workspace?.id!==id&&!confirm(window.agmsTranslate?.('Discard unsaved layout changes?')||'Discard unsaved layout changes?')){$('workspaceSelect').value=workspace.id;return}
 window.agmsLayoutEditing=false;snapshot=null;pending.clear();dirty=false;await originalOpenWorkspace(id);controls();
};
save=finish;$('saveNavigation').onclick=finish;$('cancelEdit').onclick=discard;
addItem=group=>editEntry(null,group?'group':'embed');window.agmsEditEntry=editEntry;
function move(item,direction){if(!allowed()||!window.agmsLayoutEditing)return;const siblings=items.filter(x=>item.url?x.parent_id===item.parent_id:!x.url);const target=siblings[siblings.indexOf(item)+direction];if(!target)return;const i=items.indexOf(item),j=items.indexOf(target);[items[i],items[j]]=[items[j],items[i]];dirty=true;redraw()}
function field(form,label,name,value='',type='text'){
 const wrap=make('label',label,'entry-field'),input=make(type==='textarea'?'textarea':type==='select'?'select':'input');
 if(!['textarea','select'].includes(type))input.type=type;
 input.name=name;input.value=value??'';input.setAttribute('aria-label',label);wrap.append(input);form.append(wrap);return input;
}
function options(select,values,value){for(const [id,title] of values){const o=make('option',title);o.value=id;select.append(o)}select.value=value}
async function editEntry(original,initial='embed'){
 if(!allowed()||!window.agmsLayoutEditing)return;
 const isNew=!original,draft=original?{...original}:{id:crypto.randomUUID(),parent_id:initial==='group'?null:selectedGroup,title:'',icon:initial==='group'?'▤':'◈',url:null,min_role:'viewer',open_mode:initial};
 const dialog=make('dialog',undefined,'remote-dialog entry-dialog'),form=make('form',undefined,'entry-form');
 const title=make('h2',isNew?'Create entry':original.url?'Edit tile':'Edit group');form.append(title);
 const grid=make('div',undefined,'entry-grid');form.append(grid);
 const type=field(grid,'Entry type','entry_type','','select');
 const kinds=[['group','Group'],['embed','WebUI (iFrame)'],['proxy','AGMS Proxy'],['external','External link'],['ssh','SSH terminal']];
 if(window.agmsAccountRole==='admin')kinds.push(['rdp','RDP (Guacamole)']);
 options(type,kinds,original?(original.url?original.open_mode||'embed':'group'):initial);
 // Changing between a group and a service could orphan children. Service modes stay switchable.
 if(original&&!original.url)type.disabled=true;
 if(original?.url)type.querySelector('[value="group"]')?.remove();
 const name=field(grid,'Name','title',draft.title);name.required=true;name.maxLength=80;
 const parent=field(grid,'Group','parent_id','','select');options(parent,[['','No group'],...items.filter(x=>!x.url&&x.id!==draft.id).map(x=>[x.id,x.title])],draft.parent_id||'');
 const url=field(grid,'WebUI URL','url',draft.url&&!['ssh','rdp'].includes(draft.open_mode)?draft.url:'','url');
 const icon=field(grid,'Icon: emoji or HTTPS image URL','icon',draft.icon_url||draft.icon);icon.maxLength=2048;
 const color=field(grid,'Tile color','color',draft.color||'#243b5a','color');
 const minRole=field(grid,'Minimum role to open','min_role','','select');options(minRole,(role==='owner'?['viewer','editor','owner']:['viewer','editor']).map(x=>[x,x]),draft.min_role||'viewer');
 const favWrap=make('label',undefined,'web-config-check'),favorite=make('input');favorite.type='checkbox';favorite.checked=!!draft.favorite;favorite.name='favorite';favWrap.append(favorite,document.createTextNode('Show as favorite'));grid.append(favWrap);
 const remote=make('fieldset',undefined,'entry-remote');remote.append(make('legend','Connection settings'));form.append(remote);
 const remoteGrid=make('div',undefined,'entry-grid');remote.append(remoteGrid);
 const fields={};for(const [key,label,kind] of [['host','Host','text'],['port','Port','number'],['username','Username','text'],['password','Password','password'],['private_key','SSH private key','textarea'],['passphrase','SSH key passphrase','password'],['fingerprint','Server fingerprint','text'],['domain','Windows domain','text']]){
  fields[key]=field(remoteGrid,label,key,'',kind);fields[key].autocomplete='off';if(key==='port'){fields[key].min=1;fields[key].max=65535}
 }
 const hint=make('p','Leave secret fields empty to keep an unchanged connection. Verify server fingerprints through a trusted channel.');remote.append(hint);
 const status=make('p');status.role='status';form.append(status);
 if(window.agmsAccountRole==='admin')remote.append(button('Approve destination','Approve destination',async()=>{try{await api('/api/remote/targets','POST',{kind:type.value,host:fields.host.value.trim(),port:Number(fields.port.value)});status.textContent='Remote destination approved.'}catch(e){status.textContent=e.message}}));
 let configured=false,configuredKind=null,loadedMeta=null;
 const existingPending=pending.get(draft.id);let removeRequested=pending.has(draft.id)&&existingPending===null;
 const removeSecrets=button('Remove saved credentials','Remove saved credentials',()=>{removeRequested=true;for(const key of ['password','private_key','passphrase','domain'])fields[key].value='';status.textContent='Credentials will be removed when you apply and save the layout.';removeSecrets.disabled=true});removeSecrets.hidden=true;remote.append(removeSecrets);
 if(existingPending){for(const [key,input] of Object.entries(fields))input.value=existingPending[key]??'';configured=true;configuredKind=existingPending.kind}
 let priorMode=type.value;
 function mode(){
  const kind=type.value,isGroup=kind==='group',isRemote=['ssh','rdp'].includes(kind);
  parent.parentElement.hidden=isGroup;parent.disabled=isGroup;favWrap.hidden=isGroup;
  url.parentElement.hidden=isGroup||isRemote;url.disabled=isGroup||isRemote;url.required=!isGroup&&!isRemote;
  remote.hidden=!isRemote;for(const [key,input] of Object.entries(fields)){
   const hidden=!isRemote||(kind==='rdp'&&['private_key','passphrase'].includes(key))||(kind==='ssh'&&key==='domain');
   input.parentElement.hidden=hidden;input.disabled=hidden;input.required=!hidden&&['host','port','username'].includes(key);
  }
  fields.fingerprint.required=kind==='ssh';fields.fingerprint.placeholder=kind==='ssh'?'SHA256:…':'64 hexadecimal digits (optional)';
  if(priorMode!==kind||!fields.port.value)fields.port.value=kind==='rdp'?'3389':'22';priorMode=kind;
 }
 type.onchange=mode;mode();
 const actions=make('div',undefined,'entry-actions');
 if(original){
  actions.append(button('Duplicate','Duplicate',()=>{const copy={...draft,id:crypto.randomUUID(),title:name.value.trim()+' (Copy)'};items.push(copy);if(!original.url){for(const child of items.filter(x=>x.parent_id===original.id))items.push({...child,id:crypto.randomUUID(),parent_id:copy.id})}dirty=true;dialog.close();redraw()}));
  actions.append(button('Delete','Delete',()=>{if(!confirm(window.agmsTranslate?.('Delete this entry and its contents?')||'Delete this entry and its contents?'))return;const removed=new Set(items.filter(x=>x.id===draft.id||x.parent_id===draft.id).map(x=>x.id));items=items.filter(x=>!removed.has(x.id));for(const id of removed)pending.delete(id);if(removed.has(selectedGroup))selectedGroup=null;dirty=true;dialog.close();redraw()}));
 }
 actions.append(button('Cancel','Cancel',()=>dialog.close()));const submit=make('button','Apply','agms-button primary');submit.type='submit';actions.append(submit);form.append(actions);
 form.onsubmit=e=>{
  e.preventDefault();const kind=type.value;if(!name.value.trim())return name.focus();
  if(!['group','ssh','rdp'].includes(kind)){
   try{const u=new URL(url.value);if(!['http:','https:'].includes(u.protocol)||!u.hostname||u.username||u.password||(kind==='proxy'&&(u.protocol!=='https:'||u.hash)))throw Error();}catch{status.textContent='Enter a valid WebUI URL. Proxy requires HTTPS without a fragment.';return}
  }
  const iconValue=icon.value.trim();if(/^https?:\/\//i.test(iconValue)&&!/^https:\/\//i.test(iconValue)){status.textContent='Image URLs must use HTTPS.';return}
  const updated={...draft,title:name.value.trim(),parent_id:kind==='group'?null:parent.value||null,open_mode:kind==='group'?'embed':kind,url:kind==='group'?null:['ssh','rdp'].includes(kind)?kind+'://connection':url.value.trim(),min_role:minRole.value,favorite:kind!=='group'&&favorite.checked,color:color.value,icon_url:/^https:\/\//i.test(iconValue)?iconValue:'',icon:/^https:\/\//i.test(iconValue)?draft.icon:iconValue};
  if(['ssh','rdp'].includes(kind)){
   const config={kind};for(const [key,input] of Object.entries(fields))config[key]=input.disabled?'':key==='port'?Number(input.value):input.value;
   if(removeRequested&&!config.password&&!config.private_key){pending.set(draft.id,null)}else{
   const sameDestination=configured&&configuredKind===kind&&(!loadedMeta||['host','port','username'].every(key=>(key==='host'?String(config[key]).toLowerCase():String(config[key]))===(key==='host'?String(loadedMeta[key]).toLowerCase():String(loadedMeta[key]))));
   if(!sameDestination&&!config.password&&!config.private_key){status.textContent='Enter a password or SSH private key.';return}
   if(kind==='ssh'&&!/^SHA256:[A-Za-z0-9+/]{43}=?$/.test(config.fingerprint)){status.textContent='SSH host key SHA256 fingerprint is required';return}
   if(kind==='rdp'&&config.fingerprint&&!/^(?:[A-Fa-f0-9]{64}|(?:[A-Fa-f0-9]{2}:){31}[A-Fa-f0-9]{2})$/.test(config.fingerprint)){status.textContent='Use the RDP certificate SHA256 fingerprint (64 hexadecimal digits)';return}
   if(existingPending||!loadedMeta||['host','port','username','fingerprint'].some(key=>String(config[key])!==String(loadedMeta[key]))||['password','private_key','passphrase','domain'].some(key=>config[key]))pending.set(draft.id,config);
   }
  }else pending.delete(draft.id);
  if(original)items[items.findIndex(x=>x.id===draft.id)]=updated;else items.push(updated);
  dirty=true;dialog.close();redraw();
 };
 dialog.append(form);document.body.append(dialog);dialog.addEventListener('close',()=>{form.reset();dialog.remove()},{once:true});dialog.showModal();name.focus();
 if(original&&['ssh','rdp'].includes(original.open_mode)&&!existingPending){
  // Metadata only: the API never returns a password or private key.
  submit.disabled=true;
  try{const config=await api('/api/workspaces/'+workspace.id+'/remote/'+draft.id);if(dialog.isConnected&&type.value===original.open_mode&&config.kind===original.open_mode){configured=!!config.configured;configuredKind=config.kind;loadedMeta=config;removeSecrets.hidden=!configured;removeSecrets.disabled=removeRequested;for(const key of ['host','port','username','fingerprint'])if(config[key]!==undefined&&!fields[key].value)fields[key].value=config[key];fields.port.value=config.port;}}
  catch(e){if(dialog.isConnected)status.textContent=e.message}finally{submit.disabled=false}
 }
}
function dimensionsFor(item,placement){return placement==='favorites'?['favorite_width','favorite_height']:['tile_width','tile_height']}
function size(item,placement){
 if(!window.agmsLayoutEditing||!allowed())return;
 const keys=dimensionsFor(item,placement),dialog=make('dialog',undefined,'remote-dialog'),form=make('form',undefined,'remote-form');form.append(make('h2','Tile size'));
 const selects=[];for(const [key,title] of [[keys[0],'Width'],[keys[1],'Height']]){const select=field(form,title,key,'','select');options(select,[1,2,3,4].map(i=>[String(i),String(i)]),String(item[key]||1));selects.push(select)}
 form.append(make('p',placement==='favorites'?'This size applies only to this favorite on the overview.':'This size applies only to this tile in its group or homepage.'));
 const submit=make('button','Apply');submit.type='submit';submit.className='agms-button primary';form.append(submit,button('Close','Close',()=>dialog.close()));
 form.onsubmit=e=>{e.preventDefault();for(const select of selects)item[select.name]=Number(select.value);dirty=true;dialog.close();redraw()};dialog.append(form);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();
}
const originalTile=tile;
tile=function(item,placement='main'){
 placement=placement==='favorites'?'favorites':'main';
 const node=originalTile(item);node.draggable=false;const [width,height]=dimensionsFor(item,placement);
 const shell=make('article',undefined,'layout-tile-shell');shell.dataset.layoutId=item.id;shell.dataset.placement=placement;shell.dataset.width=item[width]||1;shell.style.gridRow='span '+2*(item[height]||1);shell.append(node);
 if(window.agmsLayoutEditing&&allowed()){
  const tools=make('div',undefined,'layout-tile-controls');const grip=button('⠿','Move tile',()=>{});grip.classList.add('layout-drag-handle');
  tools.append(grip,button('↑','Move tile up',()=>move(item,-1)),button('↓','Move tile down',()=>move(item,1)),button('Size','Tile size',()=>size(item,placement)),button('✎',item.url?'Edit tile':'Edit group',()=>editEntry(item)));shell.append(tools);
  const resize=button('◢','Resize tile',()=>size(item,placement));resize.classList.add('layout-resize-handle');shell.append(resize);drag(item,shell,grip,false,placement);drag(item,shell,resize,true,placement);
  node.onclick=()=>{if(!item.url)showGroup(item.id)};
 }
 return shell;
};
function drag(item,shell,handle,resizing,placement){
 handle.addEventListener('pointerdown',e=>{
  if(!window.agmsLayoutEditing||!allowed()||e.button!==0)return;
  handle.setPointerCapture(e.pointerId);const [width,height]=dimensionsFor(item,placement),start={x:e.clientX,y:e.clientY,w:item[width]||1,h:item[height]||1};
  let moved=false,target=null;const step=Math.max(100,$('tiles').clientWidth/Math.max(1,Math.floor(($('tiles').clientWidth+15)/205)));shell.classList.add('layout-dragging');
  function move(event){
   if(Math.abs(event.clientX-start.x)+Math.abs(event.clientY-start.y)>8)moved=true;if(!moved)return;
   if(resizing){item[width]=Math.max(1,Math.min(4,start.w+Math.round((event.clientX-start.x)/step)));item[height]=Math.max(1,Math.min(4,start.h+Math.round((event.clientY-start.y)/144)));shell.dataset.width=item[width];shell.style.gridRow='span '+2*item[height];dimensions()}
   else{const hit=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-layout-id]');target?.classList.remove('layout-drop-target');target=hit&&hit!==shell&&hit.dataset.placement===placement?hit:null;target?.classList.add('layout-drop-target');if(event.clientY>innerHeight-70)scrollBy(0,14);else if(event.clientY<80)scrollBy(0,-14)}
  }
  function end(){
   shell.classList.remove('layout-dragging');target?.classList.remove('layout-drop-target');handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);
   if(moved){handle.addEventListener('click',event=>{event.preventDefault();event.stopImmediatePropagation()},{once:true,capture:true});if(!resizing&&target){const other=items.find(x=>x.id===target.dataset.layoutId);if(other&&other.parent_id===item.parent_id){const from=items.indexOf(item),to=items.indexOf(other);items.splice(from,1);items.splice(to,0,item)}}dirty=true;redraw()}
  }
  handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
 });
}
function dimensions(){for(const root of document.querySelectorAll('.web-tiles')){const columns=Math.max(1,Math.floor((root.clientWidth+15)/205));for(const shell of root.querySelectorAll(':scope>.layout-tile-shell'))shell.style.gridColumn='span '+Math.min(columns,Number(shell.dataset.width)||1)}}
const originalShowHome=showHome,originalShowGroup=showGroup;
showHome=function(){originalShowHome();controls()};showGroup=function(id){originalShowGroup(id);controls()};$('showHome').onclick=()=>showHome();
// Group order is editable directly in the sidebar, including inside a group.
function dragGroup(item,row,handle){
 handle.addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();move(item,event.key==='ArrowUp'?-1:1);$('groupNav').querySelector('[data-group-id="'+CSS.escape(item.id)+'"] .layout-drag-handle')?.focus()}});
 handle.addEventListener('pointerdown',event=>{
  if(!allowed()||!window.agmsLayoutEditing||event.button!==0)return;
  event.preventDefault();handle.setPointerCapture(event.pointerId);
  const start={x:event.clientX,y:event.clientY};let moved=false,target=null;
  function motion(e){
   if(Math.abs(e.clientX-start.x)+Math.abs(e.clientY-start.y)>8)moved=true;if(!moved)return;
   row.classList.add('layout-dragging');target?.classList.remove('layout-drop-target');
   const hit=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-group-id]');target=hit&&hit!==row?hit:null;target?.classList.add('layout-drop-target');
   if(e.clientY>innerHeight-60)scrollBy(0,14);else if(e.clientY<60)scrollBy(0,-14);
  }
  function end(e){
   handle.removeEventListener('pointermove',motion);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);
   row.classList.remove('layout-dragging');target?.classList.remove('layout-drop-target');
   if(e.type==='pointercancel'||!moved||!target)return;
   const other=items.find(x=>x.id===target.dataset.groupId&&!x.url);if(!other)return;
   const from=items.indexOf(item),to=items.indexOf(other);items.splice(from,1);items.splice(to,0,item);dirty=true;redraw();
  }
  handle.addEventListener('pointermove',motion);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
 });
}
const originalRenderNav=renderNav;renderNav=function(){
 originalRenderNav();if(!window.agmsLayoutEditing||!allowed())return;
 const groups=items.filter(n=>!n.url);
 Array.from($('groupNav').children).forEach((node,index)=>{
  const group=groups[index],row=make('div',undefined,'layout-group-row');row.dataset.groupId=group.id;
  const grip=button('⠿','Move group',()=>{});grip.classList.add('layout-drag-handle');
  const up=button('↑','Move group up',()=>move(group,-1)),down=button('↓','Move group down',()=>move(group,1));up.disabled=index===0;down.disabled=index===groups.length-1;
  const actions=make('div',undefined,'layout-group-controls');actions.append(up,down,button('✎','Edit group',()=>editEntry(group)));
  node.replaceWith(row);row.append(grip,node,actions);dragGroup(group,row,grip);
 });
};
const observer=new MutationObserver(dimensions);observer.observe($('tiles'),{childList:true});observer.observe($('agmsFavorites'),{childList:true,subtree:true});window.addEventListener('resize',dimensions);
window.addEventListener('beforeunload',e=>{if(window.agmsLayoutEditing&&dirty){e.preventDefault();e.returnValue=''}});controls();if(workspace)redraw();
})();
