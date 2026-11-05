/* SPDX-License-Identifier: GPL-3.0-or-later */
(function(){'use strict';
const K=customElements.get('omni-keyboard'),P=OmniPrediction,oldShow=K.prototype.show,oldCommand=K.prototype.command,oldHandle=K.prototype.handle;
K.prototype.suggest=function(){
 const box=this.querySelector('.kb-suggestions');if(!box)return;box.replaceChildren();box.hidden=this.privateField||this.mode==='password';if(box.hidden)return;
 const list=P.candidates({value:this.value,cursor:this.cursor,locale:this.locale,mode:this.mode,privateField:this.privateField,history:this.history,recentURLs:this.recentURLs||[]},OmniWords);
 for(const row of list){const b=document.createElement('button');b.type='button';b.textContent=row.text;b.title=row.kind;b.addEventListener('click',e=>{e.stopPropagation();const applied=P.apply(this.value,row,this.maxLength);if(applied){Object.assign(this,applied);this.sync();this.querySelector('[data-key]')?.focus();}else this.querySelector('.kb-message').textContent='Text limit reached';});box.append(b);}
 if(!list.length){const note=document.createElement('span');note.textContent='Local suggestions · nothing leaves this device';box.append(note);}
};
K.prototype.show=function(options){
 this.privateField=!!options.privateField||options.mode==='password';this.recentURLs=this.privateField?[]:(options.recentURLs||[]).filter(x=>typeof x==='string').slice(0,100);this.pasteQueue=[];
 oldShow.call(this,{...options,history:this.privateField?[]:options.history});
 let button=this.querySelector('.queue-open');if(!button){button=document.createElement('button');button.type='button';button.className='queue-open';button.textContent='Paste queue';button.addEventListener('click',()=>this.openQueue());this.querySelector('.kb-bar').append(button);}
 button.disabled=this.privateField;button.setAttribute('aria-label',this.privateField?'Paste queue unavailable for private fields':'Open received text queue');this.setPasteQueue(options.sessionId,options.pasteQueue||[]);
};
K.prototype.setPasteQueue=function(sessionId,entries){if(this.hidden||this.privateField||this.session.sessionId!==sessionId)return false;this.pasteQueue=P.queue(entries);return true;};
K.prototype.setCandidates=function(sessionId,values){if(this.hidden||this.privateField||this.mode==='password'||sessionId!==this.session.sessionId||!Array.isArray(values))return false;this.history=values.filter(x=>typeof x==='string'&&x.length<=this.maxLength).slice(0,100);this.suggest();return true;};
K.prototype.openQueue=function(){
 if(this.privateField||this.hidden)return false;
 if(this.queueDialog?.open)return true;
 this.pasteQueue=P.queue(this.pasteQueue);
 const dialog=document.createElement('dialog');dialog.className='queue-dialog';dialog.setAttribute('aria-label','Received text');
 const title=document.createElement('h2');title.textContent='Received text';dialog.append(title);
 const note=document.createElement('p');note.textContent='Choose a message to paste. It will not open or submit automatically.';dialog.append(note);
 if(!this.pasteQueue.length){const empty=document.createElement('p');empty.textContent='No received text. Phone sharing must be enabled separately.';dialog.append(empty);}
 for(const entry of this.pasteQueue){const b=document.createElement('button');b.type='button';b.textContent=entry.label+' · '+entry.text;b.onclick=()=>{if(entry.expiresAt<=Date.now()){b.disabled=true;note.textContent='This message expired.';return;}if(this.value.length+entry.text.length>this.maxLength){note.textContent='This message exceeds the text limit.';return;}this.insert(entry.text);this.dispatchEvent(new CustomEvent('omnibloom-keyboard-queue-used',{bubbles:true,detail:{version:1,...this.session,id:entry.id}}));this.pasteQueue=this.pasteQueue.filter(x=>x.id!==entry.id);dialog.close();};dialog.append(b);}
 const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Cancel';cancel.onclick=()=>dialog.close();dialog.append(cancel);
 dialog.addEventListener('close',()=>{dialog.remove();this.queueDialog=null;this.querySelector('.queue-open')?.focus();});
 dialog.addEventListener('keydown',e=>{const a={ArrowDown:'down',ArrowUp:'up',ArrowRight:'right',ArrowLeft:'left',Escape:'circle'}[e.key];if(a){e.preventDefault();e.stopPropagation();this.handle(a);}});
 this.append(dialog);this.queueDialog=dialog;dialog.showModal();dialog.querySelector('button')?.focus();return true;
};
K.prototype.handle=function(action){
 const dialog=this.queueDialog;if(!dialog?.open)return oldHandle.call(this,action);
 action=({a:'cross',b:'circle'})[action]||action;const list=[...dialog.querySelectorAll('button:not(:disabled)')],index=list.indexOf(document.activeElement);
 if(action==='circle'){dialog.close();return true;}if(action==='cross'){if(index>=0)list[index].click();return true;}
 if(['up','down','left','right'].includes(action)){list[(index+(['up','left'].includes(action)?-1:1)+list.length)%list.length]?.focus();return true;}return true;
};
K.prototype.command=function(command){oldCommand.call(this,command);if(['submit','cancel'].includes(command)){this.queueDialog?.close();this.pasteQueue=[];this.recentURLs=[];this.querySelector('.kb-suggestions').replaceChildren();}};
})();
