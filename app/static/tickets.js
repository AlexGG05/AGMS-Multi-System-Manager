(()=>{
const trigger=document.getElementById('createTicket');
if(!trigger)return;
const dialog=document.createElement('dialog');
dialog.style.cssText='box-sizing:border-box;width:min(440px,calc(100vw - 32px));border:1px solid #52647c;border-radius:14px;background:#101c2e;color:white;padding:24px';
dialog.innerHTML='<form id="ticketForm" style="display:grid;gap:16px"><h2>Create Ticket</h2><label>Subject<input name="subject" required maxlength="200" style="display:block;width:100%;box-sizing:border-box;padding:10px"></label><label>Category<select name="category" style="display:block;width:100%;padding:10px"><option value="problem">Problem</option><option value="idea">Idea</option><option value="wish">Wish</option><option value="other">Other</option></select></label><label>Description<textarea name="description" required maxlength="10000" rows="6" style="display:block;width:100%;box-sizing:border-box;padding:10px;resize:vertical"></textarea></label><p id="ticketStatus" role="status"></p><div><button type="submit">Submit ticket</button> <button type="button" id="cancelTicket">Cancel</button></div></form>';
document.body.append(dialog);
const form=dialog.querySelector('form'),status=dialog.querySelector('#ticketStatus');
trigger.onclick=()=>{form.reset();status.textContent='';dialog.showModal()};
dialog.querySelector('#cancelTicket').onclick=()=>dialog.close();
form.onsubmit=async e=>{
 e.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;status.textContent='';
 try{
 const token=decodeURIComponent((document.cookie.match(/(?:^|; )csrf=([^;]*)/)||[])[1]||'');
 const res=await fetch('/api/tickets',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({subject:form.elements.subject.value,category:form.elements.category.value,description:form.elements.description.value})});
 if(!res.ok)throw Error('Could not create ticket. Please try again.');
 form.reset();status.textContent='Ticket created. Thank you!';
 }catch(e){status.textContent=e.message}finally{submit.disabled=false}
};
})();

(()=>{
const labels={open:'Open',in_progress:'In progress',resolved:'Resolved',waiting_for_feedback:'Waiting for feedback'};
window.agmsTicketStatus=labels;
const element=(tag,text,raw=false)=>{const node=document.createElement(tag);node.textContent=text;if(raw)node.dataset.agmsI18nIgnore='';return node};
const dialog=document.createElement('dialog');dialog.id='ticketDetails';dialog.setAttribute('aria-labelledby','ticketDetailTitle');
dialog.style.cssText='box-sizing:border-box;width:min(650px,calc(100vw - 32px));max-height:85vh;overflow:auto;border:1px solid #52647c;border-radius:14px;background:#101c2e;color:white;padding:24px';
document.body.append(dialog);
const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )csrf=([^;]*)/)||[])[1]||'');
async function request(path,method='GET',body){
 const res=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await res.json();if(!res.ok)throw Error(data.detail||'Could not load ticket.');return data;
}
window.agmsOpenTicket=async id=>{
 const data=await request('/api/tickets/'+encodeURIComponent(id));
 const ticket=data.ticket;dialog.replaceChildren();
 const title=element('h2','#'+ticket.number+' · '+ticket.subject,true);title.id='ticketDetailTitle';title.style.overflowWrap='anywhere';
 const state=element('p',labels[ticket.status]);
 const category=element('p',{problem:'Problem',idea:'Idea',wish:'Wish',other:'Other'}[ticket.category]);
 const author=element('p',(ticket.email||ticket.username)+' · '+new Date(ticket.created_at*1000).toLocaleString(),true);
 const description=element('p',ticket.description||'No description provided.',!!ticket.description);description.id='ticketDescription';description.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';
 const comments=document.createElement('div');comments.id='ticketComments';
 for(const comment of data.comments){
  const card=document.createElement('article');card.style.cssText='padding:12px;margin:8px 0;border:1px solid #52647c;border-radius:8px';
  const who=element('small',comment.author+' · '+new Date(comment.created_at*1000).toLocaleString(),true);
  const text=element('p',comment.body,true);text.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';card.append(who,text);comments.append(card);
 }
 if(!data.comments.length)comments.append(element('p','No comments yet.'));
 const notice=element('p','');notice.id='ticketDetailStatus';notice.setAttribute('role','status');
 dialog.append(title,state,category,author,element('h3','Description'),description,element('h3','Comments'),comments,notice);
 let textarea;
 if(data.can_comment){
  const label=element('label','Comment');textarea=document.createElement('textarea');textarea.name='comment';textarea.maxLength=10000;textarea.rows=5;textarea.style.cssText='display:block;width:100%;box-sizing:border-box;padding:10px;resize:vertical';label.append(textarea);dialog.append(label);
  const add=element('button','Add comment');add.type='button';
  add.onclick=async()=>{add.disabled=true;try{if(!textarea.value.trim())throw Error('Please enter a comment.');await request('/api/tickets/'+encodeURIComponent(id)+'/comments','POST',{comment:textarea.value});await window.agmsOpenTicket(id);window.dispatchEvent(new Event('agms-ticket-updated'))}catch(e){notice.textContent=e.message}finally{add.disabled=false}};
  dialog.append(add);
 }
 if(data.can_manage){
  const select=document.createElement('select');select.id='ticketStatusSelect';
  for(const [value,text] of Object.entries(labels)){const option=element('option',text);option.value=value;select.append(option)}select.value=ticket.status;
  const label=element('label','Status');label.style.cssText='display:block;margin-top:16px';label.append(select);dialog.append(label);
  const save=element('button','Save status');save.type='button';
  save.onclick=async()=>{save.disabled=true;try{if(textarea.value.trim()){await request('/api/tickets/'+encodeURIComponent(id)+'/comments','POST',{comment:textarea.value});textarea.value='';}await request('/api/admin/tickets/'+encodeURIComponent(id)+'/status','PUT',{status:select.value});await window.agmsOpenTicket(id);window.dispatchEvent(new Event('agms-ticket-updated'))}catch(e){notice.textContent=e.message}finally{save.disabled=false}};
  dialog.append(save);
 }
 const close=element('button','Close');close.type='button';close.onclick=()=>dialog.close();dialog.append(close);
 if(!dialog.open)dialog.showModal();
};
async function loadOwnTickets(){
 const list=document.getElementById('ownTickets');if(!list)return;
 try{const data=await request('/api/tickets');list.replaceChildren();for(const ticket of data.tickets){const row=document.createElement('button');row.type='button';row.style.cssText='display:block;width:100%;text-align:left;padding:16px;margin:8px 0;overflow-wrap:anywhere';row.append(element('span','#'+ticket.number+' · '+ticket.subject,true),document.createTextNode(' · '),element('span',labels[ticket.status]));row.onclick=()=>window.agmsOpenTicket(ticket.id).catch(e=>document.getElementById('ticketPageStatus').textContent=e.message);list.append(row)}if(!data.tickets.length)list.textContent='No tickets found.'}catch(e){document.getElementById('ticketPageStatus').textContent=e.message}
}
window.addEventListener('agms-ticket-updated',loadOwnTickets);
if(document.getElementById('ownTickets')){loadOwnTickets();const id=new URLSearchParams(location.search).get('ticket');if(id)window.agmsOpenTicket(id).catch(e=>document.getElementById('ticketPageStatus').textContent=e.message)}
})();
