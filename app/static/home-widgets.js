/* Compact service summaries. Profile choices and integration APIs remain unchanged. */
(()=>{'use strict';
const root=document.getElementById('homeWidgets');if(!root)return;
const {el,api}=AGMSUI;let busy=false;
const labels={tickets:'My tickets',status:'Service status',expiry:'Expiry warnings',proxmox:'Proxmox',arcane:'Arcane',sabnzbd:'SABnzbd'};
const subtitles={proxmox:'Virtualization',arcane:'Container overview',sabnzbd:'Download queue'};
const fields={open:'Open',in_progress:'In progress',waiting_for_feedback:'Waiting for feedback',resolved:'Resolved',online:'Online',offline:'Offline',degraded:'Degraded',unknown:'Not checked',due:'Expiring within 30 days',nodes:'Nodes',cpu_percent:'CPU',ram_percent:'RAM',containers:'Containers',running:'Running',status:'Status',speed:'KB/s',sizeleft:'Remaining',timeleft:'Time remaining'};
const paths={proxmox:['M5 4l14 16M19 4L5 20'],arcane:['M12 3L3 8v9l9 5 9-5V8z','M3 8l9 5 9-5M12 13v9M7.5 5.5l9 5'],sabnzbd:['M12 3v12m-5-5l5 5 5-5','M4 16v5h16v-5'],tickets:['M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4z'],status:['M2 12h5l3-8 4 16 3-8h5'],expiry:['M12 8v5l3 2','M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18']};
function icon(kind){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('home-widget-icon');
 for(const d of paths[kind]||paths.status){const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',d);svg.append(path)}return svg;
}
const valueText=value=>value==null?'—':String(value);
function metric(list,key,label,value,{hint,translate=false}={}){
 const cell=el('div');cell.className='home-widget-metric';cell.dataset.metric=key;
 const term=el('dt',label),description=el('dd',valueText(value),!translate);if(hint){const help=el('span',hint);help.className='home-widget-metric-hint';term.append(help)}
 cell.append(term,description);list.append(cell);
}
function render(kind,result){
 const card=el('article');card.className='ops-card ops-widget home-widget';card.dataset.widget=kind;
 const header=el('header'),identity=el('div');header.className='home-widget-header';identity.className='home-widget-identity';identity.append(el('h3',labels[kind]||kind));if(subtitles[kind])identity.append(el('p',subtitles[kind]));header.append(icon(kind),identity);card.append(header);
 let message=result.error||(result.configured===false?'Integration is not configured.':!Object.keys(result).filter(key=>key!=='configured').length?'No data yet.':null);
 if(message){const note=el('p',message);note.className='home-widget-message';if(result.error)note.setAttribute('role','status');card.append(note);return card}
 const list=el('dl');list.className='home-widget-metrics';card.append(list);
 const consumed=new Set(['configured']);
 if(kind==='proxmox'){
  for(const [key,total,running,label] of [['vms','vms_total','vms_running','VMs'],['lxc','lxc_total','lxc_running','LXC']]){
   if(total in result||running in result){metric(list,key,label,valueText(result[running])+' / '+valueText(result[total]),{hint:'Running / total'});consumed.add(total);consumed.add(running)}
  }
 }
 for(const [key,value] of Object.entries(result)){
  if(consumed.has(key))continue;
  let text=valueText(value);if(value!=null&&['cpu_percent','ram_percent'].includes(key))text+=' %';
  metric(list,key,fields[key]||key,text,{translate:key==='status'});
 }
 list.style.setProperty('--metric-count',Math.min(5,list.children.length));return card;
}
window.agmsLoadWidgets=async()=>{
 if(busy||document.getElementById('homePanel').hidden)return;busy=true;
 try{const data=await api('/api/widgets');root.replaceChildren(...data.widgets.map(kind=>render(kind,data.data[kind]||{})));root.hidden=!data.widgets.length}
 catch{root.hidden=true}finally{busy=false}
};
window.agmsLoadWidgets();document.getElementById('showHome').addEventListener('click',()=>window.agmsLoadWidgets());
})();
