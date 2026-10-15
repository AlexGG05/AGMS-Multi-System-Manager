/* Remote session clients. Credentials stay on the server; tickets are single-use. */
(()=>{'use strict';
const tr=s=>window.agmsTranslate?.(s)||s;
const make=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el};
function button(text,handler){const b=make('button',text);b.type='button';b.className='agms-button secondary';b.onclick=handler;return b}
window.agmsConfigureRemote=async(wsid,item)=>{
 let config=await api('/api/workspaces/'+encodeURIComponent(wsid)+'/remote/'+encodeURIComponent(item.id));if(config.kind&&config.kind!==item.open_mode)config={configured:false};
 const dialog=make('dialog');dialog.className='remote-dialog';const form=make('form');form.className='remote-form';form.append(make('h2',item.open_mode==='ssh'?'SSH connection':'RDP connection'));
 const inputs={};
 for(const [name,label,type,value] of [['host','Host','text',config.host||''],['port','Port','number',config.port||(item.open_mode==='ssh'?22:3389)],['username','Username','text',config.username||''],['password','Password','password',''],['private_key','SSH private key','textarea',''],['passphrase','SSH key passphrase','password',''],['fingerprint','SSH host key fingerprint','text',config.fingerprint||''],['domain','Windows domain','text','']]){
  if(item.open_mode==='rdp'&&['private_key','passphrase'].includes(name)||item.open_mode==='ssh'&&name==='domain')continue;
  const wrap=make('label',name==='fingerprint'&&item.open_mode==='rdp'?'RDP certificate SHA256 fingerprint (optional)':label),input=make(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=value;input.name=name;input.autocomplete='off';input.className='agms-input';input.required=['host','port','username'].includes(name)||(name==='fingerprint'&&item.open_mode==='ssh');if(name==='port'){input.min=1;input.max=65535}if(name==='fingerprint')input.placeholder=item.open_mode==='ssh'?'SHA256:…':'64 hexadecimal digits';inputs[name]=input;wrap.append(input);form.append(wrap);
 }
 form.append(make('p','Members who can open this tile can use the saved connection. Credentials cannot be viewed. Leave secret fields empty to keep an unchanged connection.'));
 if(item.open_mode==='ssh')form.append(make('p','Verify the SSH host key fingerprint through a trusted channel before saving.'));
 else form.append(make('p','RDP uses NLA and validates the server certificate. Provide its verified SHA256 fingerprint for a self-signed certificate, or use a CA trusted by Guacamole.'));
 const status=make('p');status.role='status';const controls=make('div');controls.className='agms-toolbar-group';const save=make('button','Save connection');save.className='agms-button primary';controls.append(save);
 if(window.agmsAccountRole==='admin')controls.append(button('Approve destination',async()=>{try{await api('/api/remote/targets','POST',{kind:item.open_mode,host:inputs.host.value.trim(),port:Number(inputs.port.value)});status.textContent='Remote destination approved.'}catch(e){status.textContent=e.message}}));
 if(config.configured)controls.append(button('Remove saved credentials',async()=>{try{await api('/api/workspaces/'+wsid+'/remote/'+item.id,'DELETE');dialog.close()}catch(e){status.textContent=e.message}}));
 controls.append(button('Close',()=>dialog.close()));form.append(status,controls);dialog.append(form);document.body.append(dialog);
 dialog.addEventListener('close',()=>{form.reset();dialog.remove()},{once:true});
 form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const data={kind:item.open_mode};for(const [name,input] of Object.entries(inputs))data[name]=name==='port'?Number(input.value):input.value;await api('/api/workspaces/'+wsid+'/remote/'+item.id,'PUT',data);dialog.close();notify('Remote connection saved.')}catch(e){status.textContent=e.message}finally{save.disabled=false}};
 dialog.showModal();
};
window.agmsRemoteClient=async(host,wsid,item)=>{
 const endpoint='/api/workspaces/'+encodeURIComponent(wsid)+'/remote/'+encodeURIComponent(item.id)+'/sessions';
 const controller={closed:false,dispose(){this.closed=true;this.close?.()}};
 const note=make('p','Connecting…');note.className='remote-status';host.append(note);
 try{
  const data=await api(endpoint,'POST');if(controller.closed)return controller;
  const url=new URL('/api/remote/tunnel',location.href);url.protocol=location.protocol==='https:'?'wss:':'ws:';url.searchParams.set('ticket',data.ticket);url.searchParams.set('width',String(Math.max(320,host.clientWidth)));url.searchParams.set('height',String(Math.max(240,host.clientHeight-60)));
  if(data.kind==='ssh'){
   const area=make('div');area.className='ssh-terminal';area.dataset.agmsI18nIgnore='';host.append(area);
   const terminal=new Terminal({cursorBlink:true,scrollback:3000,fontSize:14,theme:{background:'#0b1220'},allowProposedApi:false});
   const fit=new FitAddon.FitAddon();terminal.loadAddon(fit);terminal.open(area);
   const socket=new WebSocket(url);socket.binaryType='arraybuffer';
   const send=message=>{if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(message))};
   const controls=AGMSRemoteKeys.create({host,kind:'ssh',sendSSH:data=>send({type:'input',data}),focus:()=>terminal.focus(),applicationCursor:()=>terminal.modes.applicationCursorKeysMode});
   terminal.onData(data=>controls.inputSSH(data));
   terminal.textarea?.addEventListener('blur',()=>controls.reset());
   function resize(){if(!host.isConnected)return;try{fit.fit();send({type:'resize',cols:terminal.cols,rows:terminal.rows})}catch{}}
   const observer=new ResizeObserver(resize);observer.observe(area);
   socket.onopen=()=>{controls.setEnabled(true);note.textContent='Connected';resize();terminal.focus()};
   socket.onmessage=event=>{if(typeof event.data==='string'){try{note.textContent=JSON.parse(event.data).error||''}catch{}}else terminal.write(new Uint8Array(event.data))};
   socket.onclose=()=>{controls.setEnabled(false);note.textContent='Session ended. Close this window and reopen the tile to reconnect.'};
   socket.onerror=()=>{controls.setEnabled(false);note.textContent='Remote connection failed.'};
   controller.close=()=>{controls.dispose();observer.disconnect();socket.close();terminal.dispose()};
  }else{
   const display=make('div');display.className='rdp-display';display.dataset.agmsI18nIgnore='';display.tabIndex=0;host.append(display);
   let ready=false,failed=false;
   const tunnel=new Guacamole.WebSocketTunnel(url.origin+url.pathname);const client=new Guacamole.Client(tunnel);display.append(client.getDisplay().getElement());
   let sink;const controls=AGMSRemoteKeys.create({host,kind:'rdp',sendRDP:(state,code)=>client.sendKeyEvent(state,code),focus:()=>sink.getElement().focus({preventScroll:true})});
   const keyboard=new Guacamole.Keyboard(display);keyboard.onkeydown=code=>controls.keydown(code);keyboard.onkeyup=code=>controls.keyup(code);
   display.addEventListener('focusout',event=>{if(!display.contains(event.relatedTarget)){keyboard.reset();controls.reset()}});
   const mouse=new Guacamole.Mouse(display);mouse.onmousedown=mouse.onmouseup=mouse.onmousemove=state=>{display.focus();client.sendMouseState(state,true)};
   const touch=new Guacamole.Mouse.Touchpad(display);touch.onmousedown=touch.onmouseup=touch.onmousemove=state=>client.sendMouseState(state,true);
   sink=new Guacamole.InputSink();const input=sink.getElement();input.setAttribute('aria-label','Remote keyboard input');input.autocomplete='off';input.setAttribute('autocapitalize','off');input.setAttribute('autocorrect','off');input.spellcheck=false;Object.assign(input.style,{width:'1px',height:'1px',opacity:'0',pointerEvents:'none'});display.append(input);
   // One keyboard listens to the display and its input sink, avoiding duplicate key events.
   function resize(){const d=client.getDisplay();if(d.getWidth()){d.scale(Math.min(1,display.clientWidth/d.getWidth(),display.clientHeight/d.getHeight()));if(ready)note.textContent='Connected'}client.sendSize(Math.max(320,display.clientWidth),Math.max(240,display.clientHeight))}
   const observer=new ResizeObserver(resize);observer.observe(display);client.getDisplay().onresize=resize;
   client.onerror=()=>{failed=true;ready=false;keyboard.reset();controls.setEnabled(false);note.textContent='Remote connection failed. Check NLA, certificate trust and credentials.'};
   client.onstatechange=state=>{if(state===3){ready=true;controls.setEnabled(true);resize();display.focus()}else if(state===5){ready=false;keyboard.reset();controls.setEnabled(false);if(!failed)note.textContent='Session ended. Close this window and reopen the tile to reconnect.'}};
   client.connect(url.searchParams.toString());controller.close=()=>{controls.dispose();observer.disconnect();keyboard.reset();client.disconnect()};
  }
 }catch(e){note.textContent=e.message}
 return controller;
};
})();
