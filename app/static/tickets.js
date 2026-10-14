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
