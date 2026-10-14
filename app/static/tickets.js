(()=>{
'use strict';
const labels={open:'Open',in_progress:'In progress',resolved:'Resolved',waiting_for_feedback:'Waiting for feedback'};
const priorities={low:'Low',normal:'Normal',high:'High',urgent:'Urgent'};
window.agmsTicketStatus=labels;
const el=(tag,text,raw=false)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(raw)node.dataset.agmsI18nIgnore='';return node};
const button=(text,fn,primary=false)=>{const node=el('button',text);node.type='button';node.className=primary?'agms-button primary':'agms-button secondary';node.onclick=fn;return node};
const field=(text,input)=>{const label=el('label',text);label.className='agms-field';label.append(input);return label};
const choices=(options,value)=>{const node=el('select');for(const [key,text] of Object.entries(options)){const option=el('option',text);option.value=key;node.append(option)}node.value=value;return node};
const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )csrf=([^;]*)/)||[])[1]||'');
async function request(path,method='GET',body){const res=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});const data=await res.json().catch(()=>({detail:res.status===413?'Upload rejected. Try smaller screenshots.':'Request failed'}));if(!res.ok)throw Error(data.detail||'Could not load ticket.');return data}
function newDialog(id,titleId){const dialog=el('dialog');dialog.id=id;dialog.className='agms-dialog';dialog.setAttribute('aria-labelledby',titleId);document.body.append(dialog);return dialog}
function fileInput(){const input=el('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.multiple=true;input.name='screenshots';return input}
async function screenshots(input){const files=Array.from(input.files||[]);if(files.length>3)throw Error('Choose up to 3 screenshots');return Promise.all(files.map(file=>{if(file.size>2*1024*1024)throw Error('Each screenshot must be at most 2 MB');return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve({filename:file.name,data:String(reader.result).split(',')[1]});reader.onerror=()=>reject(Error('Could not read screenshot.'));reader.readAsDataURL(file)})}))}
function badge(text,state){const span=el('span',text);span.className='agms-badge';if(state)span.dataset.state=state;return span}
function uploadField(input){const label=field('Screenshots',input);label.append(el('small','Up to 3 PNG, JPEG or WebP images, 2 MB each.'));label.lastChild.className='agms-help';return label}
const createDialog=newDialog('ticketCreate','ticketCreateTitle');
window.agmsCreateTicket=async serviceContext=>{
 const data=await request('/api/services');createDialog.replaceChildren();
 const form=el('form');form.id='ticketForm';form.className='agms-dialog-inner agms-form';
 const title=el('h2','Create Ticket');title.id='ticketCreateTitle';
 const subject=el('input');subject.name='subject';subject.required=true;subject.maxLength=200;
 const category=choices({problem:'Problem',idea:'Idea',wish:'Wish',other:'Other'},'problem');category.name='category';
 const priority=choices(priorities,'normal');priority.name='priority';
 const service=el('select');service.name='service';const general=el('option','General ticket');general.value='';service.append(general);
 for(const entry of data.services){const option=el('option',entry.workspace_name+' · '+entry.title,true);option.value=JSON.stringify({workspace_id:entry.workspace_id,service_id:entry.id});service.append(option)}
 if(serviceContext){const value=JSON.stringify({workspace_id:serviceContext.workspace_id,service_id:serviceContext.service_id});if(Array.from(service.options).some(o=>o.value===value))service.value=value}
 const description=el('textarea');description.name='description';description.rows=6;description.required=true;description.maxLength=10000;
 const files=fileInput();files.id='ticketScreenshots';
 const status=el('p','');status.id='ticketStatus';status.className='agms-notice';status.setAttribute('role','status');
 const grid=el('div');grid.className='agms-form-grid';grid.append(field('Category',category),field('Priority',priority));
 const actions=el('div');actions.className='agms-actions';const cancel=button('Cancel',()=>createDialog.close());const submit=button('Submit ticket',null,true);submit.type='submit';
 actions.append(cancel,submit);form.append(el('span','AGMS SUPPORT'),title,field('Service',service),field('Subject',subject),grid,field('Description',description),uploadField(files),status,actions);form.firstChild.className='agms-eyebrow';createDialog.append(form);
 form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;status.textContent='';try{const context=service.value?JSON.parse(service.value):{};const created=await request('/api/tickets','POST',{subject:subject.value,category:category.value,priority:priority.value,description:description.value,attachments:await screenshots(files),...context});const selectedService=service.value;form.reset();service.value=selectedService;status.textContent='Ticket created. Thank you!';window.dispatchEvent(new Event('agms-ticket-updated'));const view=button('View ticket',async()=>{createDialog.close();await window.agmsOpenTicket(created.id)});view.classList.add('ticket-view-created');actions.querySelector('.ticket-view-created')?.remove();actions.prepend(view)}catch(err){status.textContent=err.message}finally{submit.disabled=false}};
 createDialog.showModal();
};
const trigger=document.getElementById('createTicket');if(trigger)trigger.onclick=()=>window.agmsCreateTicket().catch(e=>{const status=document.getElementById('notice')||document.getElementById('ticketPageStatus');if(status)status.textContent=e.message});
const detailDialog=newDialog('ticketDetails','ticketDetailTitle');
window.agmsOpenTicket=async id=>{
 const data=await request('/api/tickets/'+encodeURIComponent(id));const ticket=data.ticket;detailDialog.replaceChildren();
 const root=el('div');root.className='agms-dialog-inner';const title=el('h2','#'+ticket.number+' · '+ticket.subject,true);title.id='ticketDetailTitle';
 const closeIcon=button('×',()=>detailDialog.close());closeIcon.className+=' agms-icon-close';closeIcon.setAttribute('aria-label','Close');
 const badges=el('div');badges.className='agms-badges';const priorityBadge=badge(priorities[ticket.priority]);priorityBadge.dataset.priority=ticket.priority;badges.append(badge(labels[ticket.status],ticket.status),badge({problem:'Problem',idea:'Idea',wish:'Wish',other:'Other'}[ticket.category]),priorityBadge);
 const author=el('p',(ticket.email||ticket.username)+' · '+new Date(ticket.created_at*1000).toLocaleString(),true);author.className='agms-help';
 root.append(closeIcon,el('span','AGMS SUPPORT'),title,badges,author);root.children[1].className='agms-eyebrow';
 if(ticket.service_title){const context=el('div');context.className='ticket-context';context.append(el('strong','Service'),el('p',ticket.service_title,true));const url=el('a',ticket.service_url,true);url.href=ticket.service_url;url.target='_blank';url.rel='noopener noreferrer';context.append(url);root.append(context)}
 if(ticket.assigned_to)root.append(el('p','Assigned to'),el('p',ticket.assigned_to,true));
 const description=el('p',ticket.description||'No description provided.',!!ticket.description);description.id='ticketDescription';description.className='agms-copy';root.append(el('h3','Description'),description);
 if(data.attachments.length){const attachments=el('div');attachments.className='ticket-screenshots';for(const image of data.attachments){const a=el('a');a.href='/api/tickets/'+encodeURIComponent(id)+'/attachments/'+encodeURIComponent(image.id);a.download=image.filename;const img=el('img');img.src=a.href;img.alt=image.filename;img.loading='lazy';a.append(img,el('span',image.filename,true));attachments.append(a)}root.append(el('h3','Screenshots'),attachments)}
 const comments=el('div');comments.id='ticketComments';comments.className='ticket-timeline';for(const comment of data.comments){const card=el('article');card.className='ticket-comment';const text=el('p',comment.body,true);text.className='agms-copy';card.append(el('small',comment.author+' · '+new Date(comment.created_at*1000).toLocaleString(),true),text);comments.append(card)}if(!data.comments.length)comments.append(el('p','No comments yet.'));root.append(el('h3','Comments'),comments);
 const notice=el('p','');notice.id='ticketDetailStatus';notice.className='agms-notice';notice.setAttribute('role','status');root.append(notice);
 let textarea,files;
 if(data.can_comment){textarea=el('textarea');textarea.name='comment';textarea.maxLength=10000;textarea.rows=4;files=fileInput();root.append(field('Comment',textarea),uploadField(files));const add=button('Add comment',async()=>{add.disabled=true;try{if(!textarea.value.trim())throw Error('Please enter a comment.');await request('/api/tickets/'+encodeURIComponent(id)+'/comments','POST',{comment:textarea.value,attachments:await screenshots(files)});await window.agmsOpenTicket(id);window.dispatchEvent(new Event('agms-ticket-updated'))}catch(e){notice.textContent=e.message}finally{add.disabled=false}});const actions=el('div');actions.className='agms-actions';actions.append(add);root.append(actions)}
 if(data.can_manage){
  const accounts=await request('/api/admin/accounts');const statusSelect=choices(labels,ticket.status);statusSelect.id='ticketStatusSelect';const prioritySelect=choices(priorities,ticket.priority);prioritySelect.id='ticketPrioritySelect';const assigned=el('select');assigned.id='ticketAssignedSelect';const unassigned=el('option','Unassigned');unassigned.value='';assigned.append(unassigned);for(const account of accounts.accounts.filter(a=>a.role==='admin')){const option=el('option',account.email||account.username,true);option.value=account.username;assigned.append(option)}if(ticket.assigned_to&&!Array.from(assigned.options).some(o=>o.value===ticket.assigned_to)){const option=el('option',ticket.assigned_to,true);option.value=ticket.assigned_to;assigned.append(option)}assigned.value=ticket.assigned_to||'';
  const grid=el('div');grid.className='agms-form-grid';grid.append(field('Status',statusSelect),field('Priority',prioritySelect));root.append(el('h3','Manage ticket'),grid,field('Assigned to',assigned));
  const save=button('Save changes',async()=>{save.disabled=true;try{const attachments=await screenshots(files);if(attachments.length&&!textarea.value.trim())throw Error('Please enter a comment.');await request('/api/admin/tickets/'+encodeURIComponent(id)+'/status','PUT',{status:statusSelect.value,priority:prioritySelect.value,assigned_to:assigned.value||null,...(textarea.value.trim()?{comment:textarea.value,attachments}:{})});textarea.value='';files.value='';await window.agmsOpenTicket(id);window.dispatchEvent(new Event('agms-ticket-updated'))}catch(e){notice.textContent=e.message}finally{save.disabled=false}},true);const actions=el('div');actions.className='agms-actions';actions.append(save);root.append(actions);
 }
 const footer=el('div');footer.className='agms-actions';footer.append(button('Close',()=>detailDialog.close()));root.append(footer);detailDialog.append(root);if(!detailDialog.open)detailDialog.showModal();
};
async function loadOwnTickets(){const list=document.getElementById('ownTickets');if(!list)return;try{const data=await request('/api/tickets');list.replaceChildren();for(const ticket of data.tickets){const row=button('',()=>window.agmsOpenTicket(ticket.id).catch(e=>document.getElementById('ticketPageStatus').textContent=e.message));row.className='agms-button agms-ticket-row';const number=el('span','#'+ticket.number,true);number.className='agms-ticket-number';const subject=el('span',ticket.subject,true);subject.className='agms-ticket-subject';row.append(number,subject,badge(labels[ticket.status],ticket.status));list.append(row)}if(!data.tickets.length)list.textContent='No tickets found.'}catch(e){document.getElementById('ticketPageStatus').textContent=e.message}}
window.addEventListener('agms-ticket-updated',loadOwnTickets);
if(document.getElementById('ownTickets')){loadOwnTickets();const id=new URLSearchParams(location.search).get('ticket');if(id)window.agmsOpenTicket(id).catch(e=>document.getElementById('ticketPageStatus').textContent=e.message)}
})();
