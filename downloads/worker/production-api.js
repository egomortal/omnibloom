/* Authenticated hybrid006 client. No native launch except explicit real job creation. */
(function(root,factory){'use strict';var api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;else root.OmniProductionApi=api;})(typeof globalThis!=='undefined'?globalThis:window,function(root){
  'use strict';
  var HEX16=/^[a-f0-9]{16}$/,HEX32=/^[a-f0-9]{32}$/,TOKEN=/^[A-Za-z0-9_-]{16,128}$/;
  var STATES=new Set(['queued','extracting','downloading','processing','cancelling','completed','failed','cancelled','interrupted']);
  var TERMINAL=new Set(['completed','failed','cancelled','interrupted']);
  function fail(code,message,detail){var error=new Error(message);error.code=code;Object.assign(error,detail||{});return error;}
  function string(value,max,empty){return typeof value==='string'&&value.length<=max&&(empty||value.length>0)&&!/[\u0000\u000b\u000c]/.test(value);}
  function utf8Length(value){
    var bytes=0;
    for(var index=0;index<value.length;index++){
      var point=value.charCodeAt(index);
      if(point>=0xD800&&point<=0xDBFF){var next=value.charCodeAt(index+1);if(!(next>=0xDC00&&next<=0xDFFF))return -1;index++;bytes+=4;}
      else if(point>=0xDC00&&point<=0xDFFF)return -1;
      else bytes+=point<=0x7F?1:point<=0x7FF?2:3;
    }
    return bytes;
  }
  function validUrl(value){
    if(typeof value!=='string'||!value||value.length>4096||!/^https?:\/\//i.test(value)||/[\s\\\u0000-\u001f\u007f]/.test(value))return false;
    var bytes=utf8Length(value);if(bytes<0||bytes>8192)return false;
    try{var authority=value.match(/^https?:\/\/([^/?#]*)/i);if(!authority||authority[1].includes('@'))return false;var parsed=new root.URL(value);return /^(https?:)$/.test(parsed.protocol)&&!!parsed.hostname&&!parsed.username&&!parsed.password&&parsed.port!=='0';}catch(_){return false;}
  }
  function validateStatus(value){
    if(!value||value.api_version!==1||value.service!=='omni-media-worker'||!Array.isArray(value.jobs)||value.jobs.length>100||value.max_pending!==8||typeof value.queue_paused!=='boolean'||typeof value.ytdlp!=='boolean'||typeof value.jdownloader!=='boolean'||!string(value.folder,4096,true)||!string(value.history_error,4096,true))throw fail('INVALID_STATUS','Worker returned an invalid status. No controls were enabled.');
    var seen=new Set();value.jobs.forEach(function(job){if(!job||(typeof job.id!=='string'||!HEX16.test(job.id))||seen.has(job.id)||!STATES.has(job.state)||!['ytdlp','jdownloader'].includes(job.engine)||typeof job.demo!=='boolean'||typeof job.audio!=='boolean'||!string(job.url,4096,true)||(job.url&&!validUrl(job.url))||!string(job.title,4096,true)||!string(job.error===undefined?'':job.error,4096,true)||(job.filepath!==undefined&&!string(job.filepath,4096,true))||(job.note!==undefined&&!string(job.note,4096,true))||(job.engine_requested!==undefined&&!['ytdlp','jdownloader'].includes(job.engine_requested))||(job.progress!==null&&(typeof job.progress!=='number'||!Number.isFinite(job.progress)||job.progress<0||job.progress>100))||(job.request_id!==undefined&&job.request_id!==null&&(typeof job.request_id!=='string'||!HEX32.test(job.request_id))))throw fail('INVALID_STATUS','Worker returned an invalid job record.');seen.add(job.id);});
    if(value.jd_lifecycle!==undefined&&(!value.jd_lifecycle||typeof value.jd_lifecycle.can_start!=='boolean'||!string(value.jd_lifecycle.status,300,true)))throw fail('INVALID_STATUS','Worker returned invalid Java availability.');
    return value;
  }
  function validateSaved(value){
    if(!value||!Array.isArray(value.links)||value.links.length>64||value.max_links!==64||typeof value.writable!=='boolean'||typeof value.persistent!=='boolean'||!string(value.error,4096,true))throw fail('INVALID_SAVED','Worker returned invalid saved links.');
    var ids=new Set();value.links.forEach(function(link){if(!link||(typeof link.id!=='string'||!HEX16.test(link.id))||ids.has(link.id)||!validUrl(link.url)||!Number.isSafeInteger(link.created_at)||link.created_at<0)throw fail('INVALID_SAVED','Worker returned an invalid saved link.');ids.add(link.id);});return value;
  }
  function normalizeJob(job){
    var result={id:job.id,url:job.url,title:job.title||'Worker job',engine:job.engine,kind:job.engine==='jdownloader'?'file':job.audio?'audio':'video',status:job.state,progress:job.progress,demo:job.demo,audio:job.audio,error:job.error||'',filepath:job.demo?'':job.filepath||'',restored:job.restored===true,note:job.demo?'':job.note||'',engine_requested:job.engine_requested||job.engine};
    // Canonical status has no bytes/speed/ETA/timestamps: leave them absent.
    return result;
  }
  function create(options){
    options=options||{};var fetcher=options.fetch||root.fetch?.bind(root),token=options.token;
    if(typeof fetcher!=='function'||!TOKEN.test(token||''))throw fail('INVALID_SESSION','A valid same-origin worker session is required.');
    var now=options.now||Date.now,renewing=null,pendingJob=null,pendingSave=null,statusFlight=null,lastSaved=null,savedAt=0,savedFailure='';
    var preferences={theme:'bloom',reduced_motion:false,sound:false};
    try{var saved=JSON.parse(options.storage?.getItem('omni.production.preferences')||'null');if(saved&&typeof saved.theme==='string'&&/^[a-z0-9]{1,32}$/.test(saved.theme))preferences.theme=saved.theme;if(typeof saved?.reduced_motion==='boolean')preferences.reduced_motion=saved.reduced_motion;}catch(_){}
    var parseToken=options.parseToken||function(html){var next=new root.DOMParser().parseFromString(html,'text/html').querySelector('meta[name="omni-session-token"]')?.content;return next;};
    function requestId(){var bytes=options.randomBytes?options.randomBytes():root.crypto.getRandomValues(new Uint8Array(16));if(!bytes||bytes.length!==16)throw fail('RANDOM_FAILED','Could not create a request identity.');return Array.from(bytes,function(value){return value.toString(16).padStart(2,'0');}).join('');}
    async function text(response,max){var length=response.headers?.get?.('content-length');if(length&&/^\d+$/.test(length)&&Number(length)>max)throw fail('INVALID_RESPONSE','Worker response exceeds its limit.');var body=await response.text();if(body.length>max)throw fail('INVALID_RESPONSE','Worker response exceeds its limit.');return body;}
    async function renewSession(){if(renewing)return renewing;renewing=(async function(){var controller=new root.AbortController(),timer=root.setTimeout(function(){controller.abort();},10000);try{var response=await fetcher('/downloads',{cache:'no-store',credentials:'same-origin',redirect:'error',signal:controller.signal});if(!response.ok)throw fail('RECONNECT_FAILED','Could not renew the worker session.');var next=parseToken(await text(response,2*1024*1024));if(!TOKEN.test(next||''))throw fail('INVALID_SESSION','Worker returned an invalid session.');if(next!==token){lastSaved=null;savedAt=0;savedFailure='Saved links require revalidation after worker restart.';}token=next;return true;}finally{root.clearTimeout(timer);renewing=null;}})();return renewing;}
    async function request(path,body){
      var controller=new root.AbortController(),timer=root.setTimeout(function(){controller.abort();},10000),mutation=body!==undefined;
      try{
        var oldToken=token;var send=function(){return fetcher(path,{method:mutation?'POST':'GET',headers:{'X-Omni-Token':token,'Content-Type':'application/json'},body:mutation?JSON.stringify(body):undefined,cache:'no-store',credentials:'same-origin',redirect:'error',signal:controller.signal});};
        var response=await send();if(response.status===403){if(token===oldToken)await renewSession();if(mutation)throw fail('SESSION_RESTARTED','Worker restarted. Check the queue, then explicitly retry. The rejected mutation was not replayed.',{ambiguous:false});response=await send();}
        var value;try{value=JSON.parse(await text(response,2*1024*1024));}catch(error){if(error.code)throw error;throw fail('INVALID_RESPONSE','Worker returned an invalid response. Check the queue before retrying.',{ambiguous:mutation});}
        if(!response.ok)throw fail('WORKER_REJECTED',string(value?.error,4096,true)?value.error:'Worker request failed ('+response.status+').',{status:response.status,ambiguous:mutation&&response.status>=500});return value;
      }catch(error){if(controller.signal.aborted)throw fail('TIMEOUT','Request timed out. Check the queue before retrying.',{ambiguous:mutation});if(error.code){if(mutation&&error.code==='INVALID_RESPONSE')error.ambiguous=true;throw error;}throw fail('NETWORK','Worker connection failed. Check the queue before retrying.',{ambiguous:mutation});}
      finally{root.clearTimeout(timer);}
    }
    async function state(config){
      if(statusFlight)return statusFlight;statusFlight=(async function(){var status=validateStatus(await request('/api/status'));var savedError=savedFailure;
        if(!lastSaved||config?.saved===true&&now()-savedAt>=1500){try{var candidate=validateSaved(await request('/api/saved-links'));if(candidate.error)throw fail('SAVED_STORAGE',candidate.error);lastSaved=candidate;savedAt=now();savedFailure='';savedError='';}catch(error){savedError=error.message;savedFailure=savedError;if(!lastSaved)lastSaved={links:[],max_links:64,writable:false,persistent:false,error:savedError};}}
        var saved=lastSaved;var capabilities={ytdlp:status.ytdlp===true,jdownloader:status.jdownloader===true||status.jd_lifecycle?.can_start===true,jdownloader_ready:status.jdownloader===true,jdownloader_status:status.jdownloader_status||status.jd_lifecycle?.status||'Unavailable',backend:status.backend||'Unknown',ffmpeg:status.ffmpeg===true,quickjs:status.quickjs===true};
        return {jobs:status.jobs.map(normalizeJob).reverse(),saved_links:saved.links.map(function(link){return {id:link.id,url:link.url,title:new root.URL(link.url).hostname,created_at:link.created_at};}),preferences:Object.assign({},preferences),capabilities:capabilities,queue_paused:status.queue_paused,folder:status.folder,history_error:status.history_error,saved_writable:saved.writable&&!savedError,saved_persistent:saved.persistent,saved_error:savedError||saved.error||'',raw:status};
      })();try{return await statusFlight;}finally{statusFlight=null;}
    }
    async function createJob(parameters,config){
      if(!parameters||!validUrl(parameters.url)||!['ytdlp','jdownloader'].includes(parameters.engine)||typeof parameters.demo!=='boolean'||typeof parameters.audio!=='boolean'||parameters.engine==='jdownloader'&&parameters.audio)throw fail('INVALID_JOB','Choose a valid HTTP(S) source, engine and mode.');
      var signature=JSON.stringify([parameters.url,parameters.engine,parameters.demo,parameters.audio]);if(!pendingJob||pendingJob.signature!==signature)pendingJob={signature:signature,id:requestId(),token:token,ambiguous:false};
      if(pendingJob.ambiguous&&pendingJob.token!==token){if(config?.confirmNewAfterRestart!==true)throw fail('AMBIGUOUS_RESTART','A previous submission may have been accepted before restart. Check history. A new submission can duplicate it.',{requiresNewSubmissionConfirmation:true});pendingJob={signature:signature,id:requestId(),token:token,ambiguous:false};}
      var attempt=pendingJob;try{var result=await request('/api/jobs',Object.assign({},parameters,{request_id:attempt.id}));if(!result||(typeof result.id!=='string'||!HEX16.test(result.id)))throw fail('INVALID_RESPONSE','Worker returned an invalid job receipt. Check the queue before retrying.',{ambiguous:true});if(pendingJob===attempt)pendingJob=null;return {id:result.id,demo:parameters.demo,request_id:attempt.id};}catch(error){if(error.ambiguous)attempt.ambiguous=true;if(error.code==='SESSION_RESTARTED'&&!attempt.ambiguous)attempt.token=token;throw error;}
    }
    async function saveLink(url){if(!validUrl(url))throw fail('INVALID_URL','Use a complete HTTP(S) link without credentials or whitespace.');if(!pendingSave||pendingSave.url!==url)pendingSave={url:url,id:requestId()};var attempt=pendingSave;var response=await request('/api/saved-links',{url:url,request_id:attempt.id});if(!response||(typeof response.id!=='string'||!HEX16.test(response.id))||typeof response.created!=='boolean'||typeof response.present!=='boolean'||typeof response.replayed!=='boolean')throw fail('INVALID_RESPONSE','Worker returned an invalid save receipt. Check saved links before retrying.');if(pendingSave===attempt)pendingSave=null;savedAt=0;lastSaved=null;return response;}
    async function cancel(id){if(typeof id!=='string'||!HEX16.test(id))throw fail('INVALID_ID','Invalid job identity.');var value=await request('/api/cancel',{id:id});if(value?.ok!==true)throw fail('INVALID_RESPONSE','Worker did not confirm cancellation.');return value;}
    async function setQueuePaused(paused){if(typeof paused!=='boolean')throw fail('INVALID_QUEUE','Queue state must be boolean.');var value=await request('/api/queue',{paused:paused});if(value?.queue_paused!==paused)throw fail('INVALID_RESPONSE','Worker did not confirm the queue state.');return value;}
    async function deleteLink(id){if(typeof id!=='string'||!HEX16.test(id))throw fail('INVALID_ID','Invalid saved-link identity.');var value=await request('/api/saved-links/delete',{id:id});if(typeof value?.removed!=='boolean')throw fail('INVALID_RESPONSE','Worker did not confirm saved-link deletion.');savedAt=0;lastSaved=null;return value;}
    function setPreferences(value){if(!value||Object.keys(value).some(function(key){return !['theme','reduced_motion','sound'].includes(key);}))throw fail('INVALID_PREFERENCES','Unsupported local preference.');if(value.theme!==undefined&&(typeof value.theme!=='string'||!/^[a-z0-9]{1,32}$/.test(value.theme)))throw fail('INVALID_PREFERENCES','Invalid theme.');['reduced_motion','sound'].forEach(function(key){if(value[key]!==undefined&&typeof value[key]!=='boolean')throw fail('INVALID_PREFERENCES','Invalid motion preference.');});Object.assign(preferences,value);try{options.storage?.setItem('omni.production.preferences',JSON.stringify(preferences));}catch(_){}return {preferences:Object.assign({},preferences)};}
    return Object.freeze({state:state,createJob:createJob,saveLink:saveLink,deleteLink:deleteLink,cancel:cancel,setQueuePaused:setQueuePaused,setPreferences:setPreferences,renewSession:renewSession,sessionTokenForTest:options.testMode?function(){return token;}:undefined});
  }
  return Object.freeze({create:create,validUrl:validUrl,validateStatus:validateStatus,validateSaved:validateSaved,normalizeJob:normalizeJob,terminal:TERMINAL});
});
