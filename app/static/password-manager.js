(()=>{
const dialog=document.createElement('dialog');dialog.id='passwordManagerDialog';dialog.setAttribute('aria-labelledby','passwordManagerTitle');dialog.className='agms-dialog agms-dialog-inner';document.body.append(dialog);
const text=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node};
window.agmsPasswordManagerSetup=({website,tab,frame})=>{
 dialog.replaceChildren();const title=text('h2','Password manager setup');title.id='passwordManagerTitle';
 dialog.append(title,text('p',"Add the following URLs to this service's vault entry. Set URI match detection to Starts with for each URL. Keep the original website URL."));
 const status=text('p','');status.setAttribute('role','status');
 const urls=[['Website URL',website],['AGMS URL',new URL(tab).origin+new URL(tab).pathname]];
 const frameUrl=new URL(frame);if(frameUrl.origin===location.origin&&frameUrl.pathname.startsWith('/web-proxy/'))urls.push(['Proxy URL',frameUrl.origin+frameUrl.pathname]);
 for(const [label,value] of urls){
  const row=text('label',label);row.style.cssText='display:block;margin:14px 0';
  const input=document.createElement('input');input.readOnly=true;input.value=value;input.dataset.agmsI18nIgnore='';input.style.cssText='display:block;width:100%;box-sizing:border-box;padding:10px';input.onclick=()=>input.select();
  const copy=text('button','Copy');copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(value);status.textContent='Copied'}catch{input.select();status.textContent='Please copy the URL manually.'}};
  row.append(input,copy);dialog.append(row);
 }
 const close=text('button','Close');close.type='button';close.onclick=()=>dialog.close();dialog.append(text('p','Suggestions and menu visibility are controlled by your browser extension.'),status,close);dialog.showModal();
};
})();
