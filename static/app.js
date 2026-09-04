function createUserToken(){
  const browserCrypto=window.crypto||window.msCrypto;
  if(browserCrypto&&typeof browserCrypto.randomUUID==="function")return browserCrypto.randomUUID();
  if(browserCrypto&&typeof browserCrypto.getRandomValues==="function"){
    const bytes=new Uint8Array(16);browserCrypto.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const hex=Array.from(bytes,value=>value.toString(16).padStart(2,"0")).join("");
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  return `user-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

const state = { items: [], rdpLinkMode: "download", userName: (localStorage.getItem("equipment-user-name") || "").trim(), userToken: localStorage.getItem("equipment-user-token") || createUserToken(), adminItem: null };
localStorage.setItem("equipment-user-token", state.userToken);
const elements = {
  total: document.getElementById("total"),
  available: document.getElementById("available"),
  booked: document.getElementById("booked"),
  equipment: document.getElementById("equipment"),
  error: document.getElementById("error"),
  filter: document.getElementById("filter"),
  refresh: document.getElementById("refresh"),
  pageTitle: document.getElementById("page-title"),
  userButton: document.getElementById("user-button"),
  nameDialog: document.getElementById("name-dialog"),
  nameForm: document.getElementById("name-form"),
  nameInput: document.getElementById("name-input"),
  nameCancel: document.getElementById("name-cancel"),
  adminDialog: document.getElementById("admin-dialog"),
  adminForm: document.getElementById("admin-form"),
  adminCode: document.getElementById("admin-code"),
  adminDescription: document.getElementById("admin-description"),
  adminCancel: document.getElementById("admin-cancel")
};

function escapeHtml(value){const node=document.createElement("div");node.textContent=value;return node.innerHTML}
function showError(message=""){elements.error.textContent=message;elements.error.hidden=!message}
function openDialog(dialog){
  if(!dialog)return;
  try{if(typeof dialog.showModal==="function"){if(!dialog.open)dialog.showModal();return}}catch(error){}
  dialog.setAttribute("open","");dialog.classList.add("dialog-fallback");document.body.classList.add("modal-open");
}
function closeDialog(dialog){
  if(!dialog)return;
  if(typeof dialog.close==="function"&&dialog.open)dialog.close();else dialog.removeAttribute("open");
  dialog.classList.remove("dialog-fallback");
  if(!document.querySelector("dialog.dialog-fallback[open]"))document.body.classList.remove("modal-open");
}
function accessTarget(value){const target=(value||"").trim();return /^[A-Za-z0-9._:-]+$/.test(target)?target:null}
function uriTarget(target){return (target.match(/:/g)||[]).length>1?`[${target}]`:target}
function bookingTimestamp(value){
  if(typeof value!=="string"||!value)return null;
  const normalized=/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)?`${value.replace(" ","T")}Z`:value;
  const timestamp=Date.parse(normalized);
  return Number.isFinite(timestamp)?timestamp:null;
}
function formatBookingAge(timestamp){
  const seconds=Math.max(0,Math.floor((Date.now()-timestamp)/1000));
  if(seconds<60)return "just now";
  if(seconds<3600){const minutes=Math.max(1,Math.round(seconds/60));return `${minutes} minute${minutes===1?"":"s"} ago`}
  if(seconds<86400){const hours=Math.max(1,Math.round(seconds/3600));return `${hours} hour${hours===1?"":"s"} ago`}
  const days=Math.max(1,Math.round(seconds/86400));return `${days} day${days===1?"":"s"} ago`;
}
function updateBookingAges(){
  document.querySelectorAll("[data-booked-timestamp]").forEach(element=>{
    const timestamp=Number(element.dataset.bookedTimestamp);
    if(Number.isFinite(timestamp))element.textContent=formatBookingAge(timestamp);
  });
}
function downloadRdp(item){
  const target=accessTarget(item.ipOrHostname);if(!target)return;
  const address=uriTarget(target);const contents=`full address:s:${address}\r\nprompt for credentials:i:1\r\n`;
  const url=URL.createObjectURL(new Blob([contents],{type:"application/x-rdp"}));const link=document.createElement("a");
  link.href=url;link.download=`${item.name.replace(/[^A-Za-z0-9._-]+/g,"-").replace(/^-|-$/g,"")||"equipment"}.rdp`;link.click();URL.revokeObjectURL(url);
}

async function load(){
  showError();
  try{
    const response=await fetch("/api/equipment",{cache:"no-store",headers:{"X-User-Name":state.userName}});
    const data=await response.json(); if(!response.ok)throw new Error(data.error||"Could not load equipment");
    const pageTitle=typeof data.pageTitle==="string"?data.pageTitle.trim():"";
    if(pageTitle){elements.pageTitle.textContent=pageTitle;document.title=pageTitle}
    state.items=data.equipment;state.rdpLinkMode=data.rdpLinkMode==="protocol"?"protocol":"download";render();
  }catch(error){showError(error.message);elements.equipment.innerHTML='<div class="empty">Could not load equipment.</div>'}
}

function render(){
  const free=state.items.filter(item=>!item.bookedByName).length;
  elements.total.textContent=state.items.length;elements.available.textContent=free;elements.booked.textContent=state.items.length-free;
  const query=elements.filter.value.trim().toLocaleLowerCase();
  const items=state.items
    .filter(item=>`${item.name} ${item.description}`.toLocaleLowerCase().includes(query))
    .sort((a,b)=>a.name.toLocaleLowerCase().localeCompare(b.name.toLocaleLowerCase()));
  if(!items.length){elements.equipment.innerHTML='<div class="empty"><strong>No equipment found</strong><br>Try a different name or description.</div>';return}
  elements.equipment.innerHTML=items.map(item=>{
    const occupied=Boolean(item.bookedByName);
    const target=accessTarget(item.ipOrHostname);
    const linkTarget=target?uriTarget(target):null;
    const titleAddress=target&&item.name.trim().toLocaleLowerCase()!==target.toLocaleLowerCase()
      ?`<span class="title-address"> · <code>${escapeHtml(target)}</code></span>`
      :'';
    const access=target&&(item.rdpEnabled||item.sshEnabled)
      ?`${item.rdpEnabled?(state.rdpLinkMode==="protocol"?`<a href="rdp://${linkTarget}">RDP</a>`:`<button type="button" data-connect="rdp" data-connect-id="${item.id}">RDP</button>`):''}${item.sshEnabled?`<a href="ssh://${linkTarget}">SSH</a>`:''}`
      :'';
    const timestamp=occupied?bookingTimestamp(item.bookedAt):null;
    const bookingMeta=occupied
      ?`<div class="booking-meta"><p class="owner"><span class="owner-who">Booked by: <strong>${escapeHtml(item.bookedByName)}${item.isMine?' (you)':''}</strong></span><span class="booking-separator" aria-hidden="true">·</span><span class="booked-age"${timestamp===null?'':` data-booked-timestamp="${timestamp}"`}>${timestamp===null?'recently':formatBookingAge(timestamp)}</span></p></div>`
      :'<div class="booking-meta booking-meta-empty" aria-hidden="true"><p class="owner"><span class="owner-who">Not booked</span><span class="booking-separator">·</span><span class="booked-age">just now</span></p></div>';
    return `<article class="card"><div class="card-top"><h3>${escapeHtml(item.name)}${titleAddress}</h3><div class="card-tools"><span class="badge ${occupied?'busy':'free'}">${occupied?'Booked':'Available'}</span>${access}</div></div><p class="description">${escapeHtml(item.description)}</p>${bookingMeta}<button class="${!occupied?'primary':item.isMine?'':'admin'}" data-id="${item.id}" data-action="${!occupied?'book':item.isMine?'release':'admin'}">${!occupied?'Book':item.isMine?'Release':'Release as administrator'}</button></article>`;
  }).join("");
  updateBookingAges();
}

async function act(item,action,adminCode=""){
  showError();const button=document.querySelector(`[data-id="${item.id}"]`);if(button)button.disabled=true;
  try{const response=await fetch("/api/equipment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,equipmentId:item.id,userToken:state.userToken,userName:state.userName,adminCode})});const data=await response.json();if(!response.ok)throw new Error(data.error||"The operation could not be completed");closeDialog(elements.adminDialog);elements.adminCode.value="";await load()}catch(error){if(button)button.disabled=false;await load();showError(error.message)}
}

elements.equipment.addEventListener("click",event=>{const connectButton=event.target.closest('button[data-connect="rdp"]');if(connectButton){const item=state.items.find(value=>value.id===Number(connectButton.dataset.connectId));if(item)downloadRdp(item);return}const button=event.target.closest("button[data-id]");if(!button)return;const item=state.items.find(value=>value.id===Number(button.dataset.id));if(!item)return;if(button.dataset.action==="book"&&!state.userName){openDialog(elements.nameDialog);elements.nameInput.focus();return}if(button.dataset.action==="admin"){state.adminItem=item;elements.adminDescription.textContent=`Enter the admin code to release “${item.name}”.`;openDialog(elements.adminDialog);elements.adminCode.focus()}else act(item,button.dataset.action)});
elements.filter.addEventListener("input",render);elements.refresh.addEventListener("click",load);
elements.userButton.addEventListener("click",()=>{state.userName="";state.userToken=createUserToken();localStorage.removeItem("equipment-user-name");localStorage.setItem("equipment-user-token",state.userToken);elements.userButton.hidden=true;elements.nameInput.value="";openDialog(elements.nameDialog);elements.nameInput.focus()});
elements.nameForm.addEventListener("submit",event=>{event.preventDefault();const name=elements.nameInput.value.trim();if(!name)return;state.userName=name;localStorage.setItem("equipment-user-name",name);elements.userButton.textContent=`${name} · Switch`;elements.userButton.hidden=false;closeDialog(elements.nameDialog);load()});
elements.nameCancel.addEventListener("click",()=>closeDialog(elements.nameDialog));
elements.adminForm.addEventListener("submit",event=>{event.preventDefault();if(state.adminItem)act(state.adminItem,"release",elements.adminCode.value)});elements.adminCancel.addEventListener("click",()=>closeDialog(elements.adminDialog));

load();
if(state.userName){elements.userButton.textContent=`${state.userName} · Switch`;elements.userButton.hidden=false}else{openDialog(elements.nameDialog)}
setInterval(updateBookingAges,60000);
setInterval(()=>{if(!document.hidden)load()},15000);
