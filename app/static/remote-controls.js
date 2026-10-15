/* Shared on-screen keys. No global shortcuts, clipboard access or persistent state. */
(function(root){'use strict';
const MODIFIERS={Shift:0xffe1,Ctrl:0xffe3,Alt:0xffe9,Super:0xffeb};
const KEYS={Esc:0xff1b,Tab:0xff09,Enter:0xff0d,Backspace:0xff08,Delete:0xffff,ArrowLeft:0xff51,ArrowUp:0xff52,ArrowRight:0xff53,ArrowDown:0xff54};
const physicalModifiers=new Set([0xffe1,0xffe2,0xffe3,0xffe4,0xffe7,0xffe8,0xffe9,0xffea,0xffeb,0xffec]);
const arrows={ArrowUp:'A',ArrowDown:'B',ArrowRight:'C',ArrowLeft:'D'};
const shifted={'1':'!','2':'@','3':'#','4':'$','5':'%','6':'^','7':'&','8':'*','9':'(','0':')','-':'_','=':'+','[':'{',']':'}','\\':'|',';':':',"'":'"',',':'<','.':'>','/':'?','`':'~'};
const number=mods=>1+(mods.Shift?1:0)+(mods.Alt?2:0)+(mods.Ctrl?4:0);
function character(key,mods){return mods.Shift?(shifted[key]||key.toUpperCase()):key}
function sshKey(key,mods={},applicationCursor=false){
 const n=number(mods);
 if(arrows[key])return n===1?'\x1b'+(applicationCursor?'O':'[')+arrows[key]:'\x1b[1;'+n+arrows[key];
 const fn=/^F([1-9]|1[0-2])$/.exec(key);
 if(fn){const i=Number(fn[1]);if(i<=4)return n===1?'\x1bO'+'PQRS'[i-1]:'\x1b[1;'+n+'PQRS'[i-1];return '\x1b['+[15,17,18,19,20,21,23,24][i-5]+(n===1?'':';'+n)+'~'}
 let result;
 if(key==='Tab')result=mods.Shift?'\x1b[Z':'\t';
 else if(key==='Esc')result='\x1b';
 else if(key==='Enter')result='\r';
 else if(key==='Backspace')result=mods.Ctrl?'\x08':'\x7f';
 else if(key==='Delete')return '\x1b[3'+(n===1?'':';'+n)+'~';
 else{
  if([...key].length!==1)return '';
  result=character(key,mods);
  if(mods.Ctrl){const code=result.toUpperCase().charCodeAt(0);if(result===' ')result='\x00';else if(result==='?')result='\x7f';else if(code>=64&&code<=95)result=String.fromCharCode(code&31)}
 }
 return (mods.Alt?'\x1b':'')+result;
}
function sshData(data,mods){
 if(!data)return data;
 const special={'\x1b[A':'ArrowUp','\x1b[B':'ArrowDown','\x1b[C':'ArrowRight','\x1b[D':'ArrowLeft','\x1bOA':'ArrowUp','\x1bOB':'ArrowDown','\x1bOC':'ArrowRight','\x1bOD':'ArrowLeft','\t':'Tab','\r':'Enter','\x7f':'Backspace','\x1b':'Esc'};
 if(special[data])return sshKey(special[data],mods);
 // Do not split an unknown escape sequence or reinterpret a bracketed paste.
 if(data.startsWith('\x1b'))return (mods.Alt?'\x1b':'')+data;
 const first=[...data][0];return sshKey(first,mods)+data.slice(first.length);
}
function keysym(key,mods={}){
 if(KEYS[key])return KEYS[key];const fn=/^F([1-9]|1[0-2])$/.exec(key);if(fn)return 0xffbd+Number(fn[1]);
 if([...key].length!==1)return null;const point=character(key,mods).codePointAt(0);return point<=255?point:0x01000000|point;
}
function rdpChord(key,mods={}){
 const code=keysym(key,mods);if(code===null)return [];
 const held=Object.keys(MODIFIERS).filter(name=>mods[name]).map(name=>MODIFIERS[name]);
 return [...held.map(k=>[k,1]),[code,1],[code,0],...held.reverse().map(k=>[k,0])];
}
function create({host,kind,sendSSH,sendRDP,focus,applicationCursor=()=>false}){
 const make=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el};
 const tools=make('div',undefined,'remote-tools');tools.hidden=true;host.append(tools);
 const layout=new ResizeObserver(()=>tools.classList.toggle('is-compact',host.clientHeight<350));layout.observe(host);
 const panel=make('div',undefined,'remote-control-panel');panel.id='remote-keys-'+(++create.serial);
 panel.hidden=!matchMedia('(pointer:coarse), (max-width:700px)').matches;
 let enabled=false;const latched=new Set(),buttons=new Map(),held=new Map(),physical=new Set();
 function button(label,fn,translated=false){const el=make('button',label,'agms-button secondary');el.type='button';if(!translated)el.dataset.agmsI18nIgnore='';el.addEventListener('pointerdown',e=>e.preventDefault());el.onclick=fn;return el}
 const keyboard=button('Keyboard',()=>{if(enabled)focus()},true),toggle=button('Special keys',()=>{panel.hidden=!panel.hidden;toggle.setAttribute('aria-expanded',String(!panel.hidden));if(panel.hidden)reset()},true);
 toggle.setAttribute('aria-controls',panel.id);toggle.setAttribute('aria-expanded',String(!panel.hidden));
 const header=make('div',undefined,'remote-control-header');header.append(keyboard,toggle);tools.append(header,panel);
 const modifiers=make('div',undefined,'remote-key-row remote-modifiers');modifiers.setAttribute('role','group');modifiers.setAttribute('aria-label','Modifiers for next key');
 const hint=make('small','Modifiers apply to the next key.','remote-key-hint');
 function reset(){latched.clear();for(const b of buttons.values())b.setAttribute('aria-pressed','false')}
 function take(){const mods=Object.fromEntries([...latched].map(name=>[name,true]));reset();return mods}
 function press(key,explicit){if(!enabled)return;const mods=explicit||take();if(explicit)reset();if(kind==='ssh')sendSSH(sshKey(key,mods,applicationCursor()));else for(const [code,state] of rdpChord(key,mods))sendRDP(state,code)}
 for(const name of (kind==='rdp'?['Ctrl','Alt','Shift','Super']:['Ctrl','Alt','Shift'])){
  const b=button(name==='Super'?'Win':name,()=>{if(!enabled)return;if(latched.has(name))latched.delete(name);else latched.add(name);b.setAttribute('aria-pressed',String(latched.has(name)))});b.setAttribute('aria-pressed','false');modifiers.append(b);buttons.set(name,b);
 }
 const functionKeys=make('div',undefined,'remote-key-row');functionKeys.hidden=true;
 const fn=button('F1–F12',()=>{functionKeys.hidden=!functionKeys.hidden;fn.setAttribute('aria-expanded',String(!functionKeys.hidden))});fn.setAttribute('aria-expanded','false');modifiers.append(fn);
 const specials=make('div',undefined,'remote-key-row');
 for(const [key,label] of [['Esc','Esc'],['Tab','Tab'],['Enter','Enter'],['ArrowLeft','←'],['ArrowDown','↓'],['ArrowUp','↑'],['ArrowRight','→'],['Delete','Del']])specials.append(button(label,()=>press(key)));
 const shortcuts=make('div',undefined,'remote-key-row');for(const [label,key,mods] of [['Ctrl+C','c',{Ctrl:true}],['Ctrl+V','v',{Ctrl:true}],['Alt+Tab','Tab',{Alt:true}],...(kind==='rdp'?[['Ctrl+Alt+Del','Delete',{Ctrl:true,Alt:true}]]:[])])shortcuts.append(button(label,()=>press(key,mods)));
 for(let i=1;i<=12;i++)functionKeys.append(button('F'+i,()=>press('F'+i)));
 panel.append(modifiers,specials,shortcuts,functionKeys,hint);
 function release(){for(const entry of held.values()){sendRDP(0,entry.code);for(const k of [...entry.mods].reverse())if(!physical.has(k))sendRDP(0,k)}held.clear();for(const code of physical)sendRDP(0,code);physical.clear()}
 return {
  element:tools,
  setEnabled(value){if(!value){release();reset()}enabled=value;tools.hidden=!value;for(const b of tools.querySelectorAll('button'))b.disabled=!value},
  inputSSH(data){if(enabled&&data)sendSSH(latched.size?sshData(data,take()):data)},
  keydown(code){
   if(!enabled)return false;
   // Physical modifier keys retain Guacamole's normal press/release behavior.
   if(physicalModifiers.has(code)){physical.add(code);sendRDP(1,code);return false}
   if(held.has(code)){sendRDP(1,held.get(code).code);return false}
   const mods=take(),keys=Object.keys(MODIFIERS).filter(name=>mods[name]).map(name=>MODIFIERS[name]).filter(code=>!physical.has(code));
   const wireCode=mods.Shift&&((code>=32&&code<=255)||(code&0xff000000)===0x01000000)?keysym(String.fromCodePoint(code&0x00ffffff),mods):code;
   for(const key of keys)sendRDP(1,key);held.set(code,{code:wireCode,mods:keys});sendRDP(1,wireCode);return false;
  },
  keyup(code){if(!enabled)return;physical.delete(code);const entry=held.get(code);sendRDP(0,entry?.code??code);for(const key of [...(entry?.mods||[])].reverse())if(!physical.has(key))sendRDP(0,key);held.delete(code)},
  reset(){release();reset()},
  dispose(){layout.disconnect();release();reset();enabled=false;tools.remove()}
 };
}
create.serial=0;
const api={sshKey,sshData,keysym,rdpChord,create};
if(typeof module==='object'&&module.exports)module.exports=api;else root.AGMSRemoteKeys=api;
})(typeof window==='object'?window:globalThis);
