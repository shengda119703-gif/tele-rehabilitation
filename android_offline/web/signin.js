(function(root){
 'use strict';
 const form=document.getElementById('signin-form'),status=document.getElementById('signin-status'),submit=document.getElementById('signin-submit'),password=document.getElementById('password'),username=document.getElementById('username');
 let register=false,active=null,cached=null,checking=false;
 function mode(value){if(active||checking)return;register=value;document.getElementById('signin-mode').setAttribute('aria-pressed',String(!value));document.getElementById('register-mode').setAttribute('aria-pressed',String(value));password.autocomplete=value?'new-password':'current-password';submit.textContent=value?'注册并登录':'登录';status.textContent='';}
 document.getElementById('signin-mode').onclick=()=>mode(false);document.getElementById('register-mode').onclick=()=>mode(true);
 function finish(){if(active)clearTimeout(active.timer);active=null;submit.disabled=false;password.value='';}
 root.PhoneSignIn={reply(id,ok,raw){if(!active||id!==active.id)return;finish();try{const value=JSON.parse(raw);if(!ok)throw Error(value.message||'登录未完成，请重试');root.PhoneAccount.activate(value,{openContact:false}).catch(e=>status.textContent=e.message);}catch(e){status.textContent=e.message;}}};
 form.onsubmit=event=>{
  event.preventDefault();if(active||checking)return;
  if(!root.OfflineAndroid?.accountAuthenticate){status.textContent='请安装最新版安卓应用';return;}
  const name=username.value.trim(),secret=password.value;if(!name||!secret){status.textContent='请填写账号和密码';return;}
  const id=crypto.randomUUID();submit.disabled=true;status.textContent=register?'正在创建账号…':'正在登录…';
  active={id,timer:setTimeout(()=>{finish();status.textContent='连接超时，请核对网络后重试';},45000)};
  try{root.OfflineAndroid.accountAuthenticate(id,name,secret,register);password.value='';}catch{finish();status.textContent='登录未完成，请重试';}
 };
 async function resume(){
  try{cached=root.PhoneAccount.identity();if(!cached)return;root.PhoneAccount.validateIdentity(cached);username.value=cached.username;checking=true;submit.disabled=true;status.textContent='正在核验登录状态…';
    const current=await root.PhoneAccount.request('session',cached);await root.PhoneAccount.activate(current,{openContact:false});
  }catch(error){status.textContent='登录状态未核验，请登录或离线进入已有账号';if(cached){const offline=document.getElementById('signin-offline');offline.hidden=false;offline.onclick=()=>root.PhoneAccount.activate(cached,{openContact:false}).catch(e=>status.textContent=e.message);}}
  finally{checking=false;submit.disabled=false;}
 }
 resume();
})(globalThis);
