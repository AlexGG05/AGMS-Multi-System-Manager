/* Dashboard grid editor: snap-to-grid drag, resize, tab sorting and persistence. */
(()=>{
const columns=12, cell=72;
const safe=s=>esc(s);
const norm=(t,i)=>({...t,x:Number.isInteger(t.x)?t.x:(i%3)*4,y:Number.isInteger(t.y)?t.y:Math.floor(i/3)*2,w:Number.isInteger(t.w)?t.w:4,h:Number.isInteger(t.h)?t.h:2});
function normalize(){dashboard.tiles=dashboard.tiles.map(norm)}
function gridCard(t,i,editable=false){
 const style='grid-column:'+ (t.x+1)+' / span '+t.w+';grid-row:'+(t.y+1)+' / span '+t.h+';';
 return '<article class="layout-card" '+(editable?'data-tile="'+i+'" draggable="true"':'')+' style="'+style+'"><strong>'+safe(t.name)+'</strong><p>'+safe(t.subtitle)+'</p>'+(editable?'<div class="layout-tools"><button data-edit="'+i+'">Edit</button><button data-delete="'+i+'">Delete</button><button data-resize="'+i+'">Size</button></div>':t.url?'<a href="'+safe(t.url)+'" target="_blank" rel="noopener noreferrer">Open ↗</a>':'')+'</article>';
}
function gridMarkup(tab,editable){
 return '<div class="layout-grid" id="layoutGrid">'+dashboard.tiles.map((t,i)=>t.tab===tab?gridCard(t,i,editable):'').join('')+'</div>';
}
function tabsMarkup(editable){
 return '<div class="dash-tabs">'+dashboard.tabs.map((t,i)=>'<button '+(editable?'draggable="true" data-tabindex="'+i+'" class="layout-tabdrag"':'class="dash-tab '+(activeTab===t?'selected':'')+'" data-tab="'+safe(t)+'"')+'>'+safe(t)+'</button>').join('')+'</div>';
}
function bindTabs(){
 document.querySelectorAll('.dash-tab').forEach(b=>b.onclick=()=>{activeTab=b.dataset.tab;render()});
}
customDashboard=function(){
 if(!dashboard)return '';
 normalize();
 return '<div class="dash-heading"><h2>'+safe(activeTab)+'</h2><button class="outline" id="editDashboard">Edit layout</button></div>'+tabsMarkup(false)+gridMarkup(activeTab,false);
};
let snapshot=null,selected=-1;
function saveState(){return JSON.stringify(dashboard)}
function cancel(){dashboard=JSON.parse(snapshot);snapshot=null;render()}
function editor(){
 normalize();
 const tab=dashboard.tabs.includes(activeTab)?activeTab:dashboard.tabs[0];
 activeTab=tab;
 const t=dashboard.tiles[selected]||{name:'',subtitle:'',url:'',tab:activeTab,w:4,h:2,x:0,y:0};
 $('content').innerHTML='<section class="panel"><h2>Layout editor</h2><p class="muted">Drag tabs to reorder. Drag cards onto the 12-column grid. Click Size to resize. Save to persist.</p>'+
 tabsMarkup(true)+'<div class="setting"><input id="layoutNewTab" placeholder="New tab"><button id="layoutAddTab">Add tab</button><button id="layoutRenameTab">Rename active tab</button><button id="layoutDeleteTab">Delete active tab</button></div>'+
 '<div class="setting"><input id="layoutName" placeholder="Title" value="'+safe(t.name)+'"><input id="layoutSubtitle" placeholder="Description" value="'+safe(t.subtitle)+'"><input id="layoutUrl" placeholder="https://..." value="'+safe(t.url)+'"><select id="layoutTab">'+dashboard.tabs.map(v=>'<option '+(v===t.tab?'selected':'')+'>'+safe(v)+'</option>').join('')+'</select><button id="layoutApply">'+(selected<0?'Add card':'Apply changes')+'</button></div>'+
 gridMarkup(activeTab,true)+'<div class="services"><button id="layoutSave">Save layout</button><button id="layoutCancel" class="outline">Cancel</button></div><p id="layoutMessage" role="status"></p></section>';
 $('layoutAddTab').onclick=()=>{const name=$('layoutNewTab').value.trim();if(!name||name.length>40||dashboard.tabs.includes(name)||dashboard.tabs.length>=20)return;dashboard.tabs.push(name);activeTab=name;selected=-1;editor()};
 $('layoutRenameTab').onclick=()=>{const name=prompt('New tab name',activeTab);if(!name||name.length>40||dashboard.tabs.includes(name))return;const old=activeTab;dashboard.tabs[dashboard.tabs.indexOf(old)]=name;dashboard.tiles.forEach(t=>{if(t.tab===old)t.tab=name});activeTab=name;editor()};
 $('layoutDeleteTab').onclick=()=>{if(dashboard.tabs.length<2)return alert('At least one tab required');if(!confirm('Delete this tab and its cards?'))return;dashboard.tabs=dashboard.tabs.filter(t=>t!==activeTab);dashboard.tiles=dashboard.tiles.filter(t=>t.tab!==activeTab);activeTab=dashboard.tabs[0];selected=-1;editor()};
 $('layoutApply').onclick=()=>{const name=$('layoutName').value.trim(),subtitle=$('layoutSubtitle').value.trim(),url=$('layoutUrl').value.trim(),tab=$('layoutTab').value;if(!name||name.length>80||subtitle.length>160||url.length>2048)return;try{if(url){const parsed=new URL(url);if(!['http:','https:'].includes(parsed.protocol)||parsed.username||parsed.password)throw Error('Invalid URL')}}catch(e){$('layoutMessage').textContent='Invalid URL';return}if(selected>=0){Object.assign(dashboard.tiles[selected],{name,subtitle,url,tab})}else{const tiles=dashboard.tiles.filter(t=>t.tab===tab);dashboard.tiles.push({name,subtitle,url,tab,x:0,y:tiles.length*2,w:4,h:2})}selected=-1;editor()};
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>{selected=Number(b.dataset.edit);editor()});
 document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>{if(!confirm('Delete card?'))return;dashboard.tiles.splice(Number(b.dataset.delete),1);selected=-1;editor()});
 document.querySelectorAll('[data-resize]').forEach(b=>b.onclick=()=>{const t=dashboard.tiles[Number(b.dataset.resize)];const w=Number(prompt('Width: 1–12 columns',t.w));const h=Number(prompt('Height: 1–12 rows',t.h));if(!Number.isInteger(w)||!Number.isInteger(h)||w<1||w>12||h<1||h>12)return;t.w=w;t.h=h;t.x=Math.min(t.x,12-w);editor()});
 let draggedTab=null;
 document.querySelectorAll('.layout-tabdrag').forEach(el=>{
 el.addEventListener('dragstart',e=>{draggedTab=Number(el.dataset.tabindex);e.dataTransfer.setData('text/plain','tab')});
 el.addEventListener('dragover',e=>e.preventDefault());
 el.addEventListener('drop',e=>{e.preventDefault();if(draggedTab===null)return;const target=Number(el.dataset.tabindex);const [item]=dashboard.tabs.splice(draggedTab,1);dashboard.tabs.splice(target,0,item);editor()});
 });
 let draggedTile=null;
 document.querySelectorAll('[data-tile]').forEach(el=>el.addEventListener('dragstart',e=>{draggedTile=Number(el.dataset.tile);e.dataTransfer.setData('text/plain','tile')}));
 const grid=$('layoutGrid');
 grid.addEventListener('dragover',e=>e.preventDefault());
 grid.addEventListener('drop',e=>{e.preventDefault();if(draggedTile===null)return;const t=dashboard.tiles[draggedTile],rect=grid.getBoundingClientRect(),colWidth=rect.width/columns;xMove(t,Math.round((e.clientX-rect.left)/colWidth),Math.round((e.clientY-rect.top)/cell));editor()});
 $('layoutCancel').onclick=cancel;
 $('layoutSave').onclick=async()=>{try{dashboard=await api('/api/dashboard',{method:'PUT',body:JSON.stringify(dashboard)});snapshot=null;selected=-1;render()}catch(e){$('layoutMessage').textContent=e.message}};
}
function xMove(t,x,y){t.x=Math.max(0,Math.min(12-t.w,x));t.y=Math.max(0,Math.min(199,y))}
dashboardEditor=function(){if(snapshot===null)snapshot=saveState();selected=-1;editor()};
})();
