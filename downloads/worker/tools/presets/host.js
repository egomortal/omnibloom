/* downloader-6: trusted bridge for the R3-043 preset panel. Uses the real same-origin worker session;
   the token never leaves this page. app.js loads only after capabilities are known (disabled on old workers). */
(function(){'use strict';
var meta=document.querySelector('meta[name="omni-session-token"]');
function load(){var s=document.createElement('script');s.src='app.js';document.body.appendChild(s);}
try{var client=OmniProductionApi.create({token:meta&&meta.content});
  window.obDownloadsHost={capabilities:{presets:false},createJob:function(p){return client.createJob(p);}};
  client.state().then(function(s){window.obDownloadsHost.capabilities=s.capabilities;}).catch(function(){}).then(load);
}catch(e){load();}
})();
