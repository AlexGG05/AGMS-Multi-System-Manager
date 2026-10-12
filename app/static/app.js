let inventory=null, pve=null, arcane=null, dashboard=null, activeTab="Main", view="overview";
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function csrf(){return document.cookie.split("; ").find(x=>x.startsWith("csrf="))?.slice(5)||""}
async function api(path,opts={}){let r=await fetch(path,{credentials:"same-origin",...opts,headers:{"Content-Type":"application/json","X-CSRF-Token":csrf(),...(opts.headers||{})}});let data=await r.json();if(!r.ok)throw Error(data.detail||data.error||"Request failed");return data}
function link(name){let url=inventory.links[name];return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(name)} ↗</a>`:esc(name)}
function cards(groups){return `<div class="grid">${groups.map(g=>`<article class="tile"><div class="row"><h3>${esc(g.name)}</h3><span class="tag">${esc(g.type)}</span></div><p>${g.items.length} configured services · live status not connected</p><div class="services">${g.items.map(i=>`<span class="service">${link(i)}</span>`).join("")}</div></article>`).join("")}</div>`}
function customDashboard(){
 if(!dashboard)return "";
 const tabs='<div class="dash-tabs">'+dashboard.tabs.map(t=>'<button class="dash-tab '+(t===activeTab?'selected':'')+'" data-tab="'+esc(t)+'">'+esc(t)+'</button>').join('')+'</div>';
 const tiles=dashboard.tiles.filter(t=>t.tab===activeTab);
 return '<div class="dash-heading"><h2>'+esc(activeTab)+'</h2><button class="outline" id="editDashboard">Edit dashboard</button></div>'+tabs+
 '<div class="grid">'+tiles.map(t=>'<article class="tile shortcut"><h3>'+esc(t.name)+'</h3><p>'+esc(t.subtitle)+'</p>'+(t.url?'<a class="launch" href="'+esc(t.url)+'" target="_blank" rel="noopener noreferrer">Open ↗</a>':'')+'</article>').join('')+'</div>';
}
function dashboardEditor(editIndex=-1){
 const tabs=dashboard.tabs;
 const selected=editIndex>=0?dashboard.tiles[editIndex]:{name:"",url:"",subtitle:"",tab:activeTab};
 $("content").innerHTML='<div class="panel"><h2>Dashboard editor</h2><p class="muted">Drag cards to reorder. Changes are saved only after clicking Save.</p><div class="setting"><input id="newTab" placeholder="New category"><button id="addTab">Add category</button></div><div class="setting"><input id="tileName" placeholder="Card name" value="'+esc(selected.name)+'"><input id="tileUrl" placeholder="https://..." value="'+esc(selected.url)+'"><input id="tileSubtitle" placeholder="Description" value="'+esc(selected.subtitle)+'"><select id="tileTab">'+tabs.map(t=>'<option value="'+esc(t)+'" '+(t===selected.tab?'selected':'')+'>'+esc(t)+'</option>').join('')+'</select><button id="addTile">'+(editIndex>=0?'Update card':'Add card')+'</button></div><div id="editorItems">'+dashboard.tiles.map((t,i)=>'<div class="setting draggable" draggable="true" data-i="'+i+'"><span>☰ '+esc(t.tab)+' / '+esc(t.name)+'</span><button class="editTile" data-i="'+i+'">Edit</button><button class="removeTile" data-i="'+i+'">Remove</button></div>').join('')+'</div><div class="services"><button id="saveDashboard">Save changes</button><button id="cancelDashboard" class="outline">Cancel</button></div><p id="editStatus" role="status"></p></div>';
 $("addTab").onclick=()=>{const t=$("newTab").value.trim();if(!t||tabs.includes(t)||t.length>40)return;tabs.push(t);dashboardEditor()};
 $("addTile").onclick=()=>{const name=$("tileName").value.trim(),url=$("tileUrl").value.trim(),subtitle=$("tileSubtitle").value.trim(),tab=$("tileTab").value;if(!name||name.length>80||subtitle.length>160)return;try{if(url&&!(new URL(url).protocol==="https:"||new URL(url).protocol==="http:"))throw Error("Invalid URL");const tile={name,url,subtitle,tab};if(editIndex>=0)dashboard.tiles[editIndex]=tile;else dashboard.tiles.push(tile);dashboardEditor()}catch(e){$("editStatus").textContent="Use a valid http(s) URL"}};
 document.querySelectorAll(".editTile").forEach(b=>b.onclick=()=>dashboardEditor(Number(b.dataset.i)));
 document.querySelectorAll(".removeTile").forEach(b=>b.onclick=()=>{dashboard.tiles.splice(Number(b.dataset.i),1);dashboardEditor()});
 let dragged=null;
 document.querySelectorAll(".draggable").forEach(el=>{
   el.addEventListener("dragstart",e=>{dragged=Number(el.dataset.i);e.dataTransfer.effectAllowed="move"});
   el.addEventListener("dragover",e=>e.preventDefault());
   el.addEventListener("drop",e=>{e.preventDefault();const target=Number(el.dataset.i);if(dragged===null||target===dragged)return;const [item]=dashboard.tiles.splice(dragged,1);dashboard.tiles.splice(target,0,item);dashboardEditor()});
 });
 $("cancelDashboard").onclick=async()=>{dashboard=await api("/api/dashboard");render()};
 $("saveDashboard").onclick=async()=>{try{dashboard=await api("/api/dashboard",{method:"PUT",body:JSON.stringify(dashboard)});render()}catch(e){$("editStatus").textContent=e.message}};
}

function render(){
 let title={overview:"Overview",docker:"Docker environments",infra:"Infrastructure",storage:"Storage / NAS",apps:"Applications",proxmox:"Proxmox cluster",settings:"Service URLs"}[view];
 $("pageTitle").textContent=title;document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
 const gs=inventory.groups, dock=gs.filter(g=>g.type==="Docker LXC"), infra=gs.filter(g=>g.type==="Infrastructure"||g.type==="Proxmox"), pi=gs.filter(g=>g.type==="Raspberry Pi");
 let html="";
 const shortcut=(name,icon)=>{const url=inventory.links[name];return '<article class="tile shortcut"><div class="shortcut-icon">'+icon+'</div><h3>'+esc(name)+'</h3><p>'+ (url?'Configured service':'Set its URL in Settings') +'</p>'+(url?'<a class="launch" target="_blank" rel="noopener noreferrer" href="'+esc(url)+'">Open application ↗</a>':'<button class="open-settings" type="button">Configure URL →</button>')+'</article>'};
 const apps=gs.flatMap(g=>g.items).filter((n,i,a)=>a.indexOf(n)===i);
 const launchpad='<div class="grid">'+apps.map(n=>shortcut(n,'◈')).join('')+'</div>';
 const environments=(arcane?.environments||[]).map(e=>'<article class="tile"><h3>'+esc(e.name)+'</h3><p>Status: '+esc(e.status)+'</p><div class="services"><span class="service">Total: '+esc(e.total??'—')+'</span><span class="service">Running: '+esc(e.running??'—')+'</span><span class="service">Stopped: '+esc(e.stopped??'—')+'</span><span class="service">Updates: '+esc(e.updates??'—')+'</span></div><div class="container-list">'+(e.containers||[]).map(x=>'<div class="container-row"><strong>'+esc(x.name)+'</strong><small>'+esc(x.state)+' · '+esc(x.image)+'</small>'+(x.hasUpdate?'<span class="tag">Update available</span>':'')+'<div class="services">'+['start','stop','restart','update'].filter(a=>a!=='update'||x.hasUpdate).map(a=>'<button class="container-action outline" data-env="'+esc(e.id)+'" data-id="'+esc(x.id)+'" data-name="'+esc(x.name)+'" data-action="'+a+'">'+a+'</button>').join('')+'</div></div>').join('')+'</div></article>').join('');
 const overviewHead='<div class="hero"><span class="eyebrow">YOUR INFRASTRUCTURE AT A GLANCE</span><h2>Welcome to CodeX Homelab</h2><p>Monitor your systems, explore Docker environments and launch your applications from one place.</p><div class="hero-actions"><button class="jump" data-target="docker">Explore Docker →</button><button class="jump secondary" data-target="apps">Open applications ↗</button></div></div>';

 const arcaneInfo=arcane?.configured ? `<div class="panel"><h3>Arcane Live</h3><p>${arcane.error?esc(arcane.error):`${arcane.environments.length} erkannte Umgebungen`}</p><div class="services">${arcane.environments.map(e=>`<span class="service">${esc(e.name)} — ${esc(e.status)}</span>`).join("")}</div><small class="muted">Read-only. Containeraktionen erst nach bestätigter API-Kompatibilität.</small></div>` : `<div class="panel">Arcane nicht konfiguriert. ARCANE_URL und ARCANE_API_KEY setzen.</div>`;
 if(view==="overview"){
   html=customDashboard()+overviewHead+`<div class="grid stats"><div class="tile"><p>Docker LXC environments</p><div class="metric">${dock.length}</div><small class="muted">Inventory count</small></div><div class="tile"><p>Listed Docker services</p><div class="metric">${dock.reduce((n,g)=>n+g.items.length,0)}</div><small class="muted">Not live container counts</small></div><div class="tile"><p>Proxmox cluster nodes</p><div class="metric">${pve?.nodes?.length??"—"}</div><small class="muted">${pve?.configured?"API configured":"Connect API to view"}</small></div><div class="tile"><p>Proxmox guests</p><div class="metric">${pve?.guests?.length??"—"}</div><small class="muted">VMs + LXCs reported by API</small></div></div><h2 class="section">Arcane environments</h2><div class="grid">${environments||'<div class="panel">No live environments available yet.</div>'}</div><h2 class="section">Docker inventory</h2>${cards(dock)}<h2 class="section">Other systems</h2>${cards([...pi,...infra])}`;
 }else if(view==="docker")html=`<h2 class="section">Live Arcane environments</h2><div class="grid">${environments||'<div class="panel">No environments reported.</div>'}</div><h2 class="section">Inventory</h2>${cards(dock)}`;
 else if(view==="infra")html=cards([...infra,...pi]);
 else if(view==="storage")html=cards(gs.filter(g=>/nas|storage|truenas/i.test(g.name+" "+g.items.join(" "))))||'<div class="panel">No NAS configured.</div>';
 else if(view==="apps")html=`<p class="muted">Your application launchpad. Add or edit links in Settings.</p>`+launchpad;
 else if(view==="proxmox"){
   html=!pve?.configured?`<div class="panel">Proxmox API not configured. Set PVE_URL, PVE_TOKEN_ID and PVE_TOKEN_SECRET in your .env file, then restart the dashboard.</div>`:
   pve.error?`<div class="panel error">${esc(pve.error)}</div>`:
   `<h2 class="section">Cluster nodes</h2><div class="grid">${pve.nodes.map(n=>`<div class="tile"><h3>${esc(n.name)}</h3><p class="${n.status==="online"?"status":"stopped"}">${esc(n.status)}</p><p>CPU ${Math.round((n.cpu||0)*100)}% · RAM ${n.maxmem?Math.round(n.mem/n.maxmem*100):0}%</p></div>`).join("")}</div><h2 class="section">VMs & LXCs</h2><div class="grid">${pve.guests.map(g=>`<div class="tile"><h3>${esc(g.name)}</h3><p>${esc(g.kind)} #${esc(g.vmid)} on ${esc(g.node)}</p><p class="${g.status==="running"?"status":"stopped"}">${esc(g.status)} · CPU ${Math.round((g.cpu||0)*100)}% · RAM ${g.maxmem?Math.round(g.mem/g.maxmem*100):0}%</p></div>`).join("")}</div>`;
 }else if(view==="settings"){
   html=`<p class="muted">Set each service's web URL. Only trusted URLs should be added; they open in a separate tab.</p><div class="panel">${gs.flatMap(g=>g.items).map((name,i)=>`<div class="setting"><strong>${esc(name)}</strong><input class="urlinput" data-name="${esc(name)}" aria-label="URL for ${esc(name)}" placeholder="https://service.example.com" value="${esc(inventory.links[name]||"")}"><button class="save" data-index="${i}">Save</button></div>`).join("")}</div><p id="saveMessage" role="status"></p>`;
 }
 $("content").innerHTML=html;
 document.querySelectorAll(".dash-tab").forEach(b=>b.onclick=()=>{activeTab=b.dataset.tab;render()});
 if($("editDashboard"))$("editDashboard").onclick=dashboardEditor;
 document.querySelectorAll(".container-action").forEach(b=>b.onclick=async()=>{
   if(!confirm(b.dataset.action.toUpperCase()+" container "+b.dataset.name+"?"))return;
   b.disabled=true;
   try{
     await api("/api/arcane/environments/"+encodeURIComponent(b.dataset.env)+"/containers/"+encodeURIComponent(b.dataset.id)+"/"+b.dataset.action,{method:"POST"});
     arcane=await api("/api/arcane");
     render();
   }catch(e){alert(e.message);b.disabled=false}
 });
 document.querySelectorAll(".jump").forEach(b=>b.onclick=()=>{view=b.dataset.target;render()});
 document.querySelectorAll(".open-settings").forEach(b=>b.onclick=()=>{view="settings";render()});
 if(view==="settings")document.querySelectorAll(".save").forEach(b=>b.onclick=async()=>{let input=document.querySelectorAll(".urlinput")[Number(b.dataset.index)];try{await api("/api/links",{method:"PUT",body:JSON.stringify({name:input.dataset.name,url:input.value})});inventory.links[input.dataset.name]=input.value;$("saveMessage").textContent="Saved "+input.dataset.name}catch(e){$("saveMessage").textContent=e.message}});
}
async function start(){let me=await api("/api/me");$("login").hidden=!!me.username;$("shell").hidden=!me.username;if(me.username){$("who").textContent=me.username;inventory=await api("/api/inventory");dashboard=await api("/api/dashboard");try{arcane=await api("/api/arcane")}catch(e){arcane={configured:true,environments:[],error:e.message}}try{pve=await api("/api/proxmox")}catch(e){pve={configured:true,error:e.message}}render()}}
$("loginForm").onsubmit=async e=>{e.preventDefault();$("loginError").textContent="";try{await api("/api/login",{method:"POST",body:JSON.stringify({username:$("username").value,password:$("password").value})});$("password").value="";await start()}catch(err){$("loginError").textContent=err.message}};
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>{view=b.dataset.view;render()});
$("logout").onclick=async()=>{await api("/api/logout",{method:"POST"});inventory=null;pve=null;arcane=null;await start()};
start().catch(e=>{$("loginError").textContent=e.message});
