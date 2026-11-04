(function(){
    'use strict';
    const results=window.omniFeatureResults=[];
    const state={phase:'idle',playback:'waiting-user',events:[],capabilities:{
        postMessage:typeof window.postMessage==='function',mediaSource:typeof window.MediaSource,
        webAssembly:typeof window.WebAssembly,secureContext:!!window.isSecureContext,
        requestMediaKeySystemAccess:typeof navigator.requestMediaKeySystemAccess
    }};
    // What sites see when choosing a quality: MSE type support, media capabilities, display.
    (function(){
        const types={};
        ['video/mp4; codecs="avc1.4d401f"','video/mp4; codecs="avc1.640028"','video/mp4; codecs="avc1.640032"',
         'video/webm; codecs="vp9"','video/webm; codecs="vp09.00.51.08"','video/mp4; codecs="av01.0.08M.08"',
         'audio/mp4; codecs="mp4a.40.2"','audio/webm; codecs="opus"'].forEach(function(t){
            try{types[t]=!!(window.MediaSource&&window.MediaSource.isTypeSupported(t));}catch(ignore){types[t]='error';}
        });
        state.capabilities.mseTypes=types;
        const sc=window.screen;
        state.capabilities.display={screen:sc?sc.width+'x'+sc.height:null,devicePixelRatio:window.devicePixelRatio,inner:window.innerWidth+'x'+window.innerHeight};
        try{
            const mc=typeof navigator!=='undefined'&&navigator.mediaCapabilities;
            if(mc&&mc.decodingInfo)[[1280,720],[1920,1080],[3840,2160]].forEach(function(size){
                mc.decodingInfo({type:'media-source',video:{contentType:'video/mp4; codecs="avc1.640028"',width:size[0],height:size[1],bitrate:size[1]*5000,framerate:30}})
                  .then(function(r){(state.capabilities.decodingInfo=state.capabilities.decodingInfo||{})[size[1]+'p']={supported:r.supported,smooth:r.smooth,powerEfficient:r.powerEfficient};render();},
                        function(){(state.capabilities.decodingInfo=state.capabilities.decodingInfo||{})[size[1]+'p']='rejected';});
            });
        }catch(ignore){}
    })();
    const automatic=window.omniYouTubeAutoTest===true;
    const requestedObservation=window.omniYouTubeObservationSeconds;
    const observationSeconds=Number.isInteger(requestedObservation)&&requestedObservation>=6&&requestedObservation<=30?requestedObservation:6;
    const deadlineSeconds=Math.min(50,Math.max(25,observationSeconds+20));
    // Keep the short diagnostic's original total bound.
    const totalSeconds=observationSeconds===6?25:deadlineSeconds;
    state.observationSeconds=observationSeconds;state.deadlineSeconds=totalSeconds;
    let totalTimer=null,observationTimer=null,finished=false,playRequested=false,observing=false;
    let player=null,script=null,readyTimer=null,playTimer=null,active=false,ready=false;
    const button=document.getElementById('play');
    function render(){document.getElementById('status').textContent=JSON.stringify(state,null,2);}
    function event(name,code){if(state.events.length<64)state.events.push({name:name,code:Number.isFinite(code)?code:null});render();}
    function result(name,pass,value){if(results.length<32)results.push({name:name,pass:pass,value:value});}
    function cleanup(){clearTimeout(totalTimer);clearTimeout(observationTimer);clearTimeout(readyTimer);clearTimeout(playTimer);readyTimer=playTimer=null;button.disabled=true;active=false;ready=false;if(script){script.remove();script=null;}if(player){try{player.destroy();}catch(ignore){}player=null;}}
    function finish(status,reason){if(!automatic||finished)return;finished=true;let snapshot=JSON.parse(JSON.stringify(state));result('YouTube official embed playback',status==='PASS',{status:status,reason:reason,snapshot:snapshot,physicalAudibility:'NOT_VERIFIED',evidence:'IFrame API playback time observation; inspect native MSE logs separately'});cleanup();render();}
    function fail(reason,code){if(!active)return;state.phase='failed';result(reason,false,Number.isFinite(code)?code:null);finish('FAIL',reason);cleanup();render();}
    function observePlayback(){
        if(!automatic||observing||!active)return;
        observing=true;state.observation={samples:[],advancedSeconds:0};
        function sample(){
            if(!active)return;
            let time,loaded=null;
            try{time=player.getCurrentTime();}
            catch(ignore){fail('playback observation API failed');return;}
            if(!Number.isFinite(time)){fail('playback time unavailable');return;}
            try{if(typeof player.getVideoLoadedFraction==='function')loaded=player.getVideoLoadedFraction();}catch(ignore){}
            try{state.quality={playback:typeof player.getPlaybackQuality==='function'?player.getPlaybackQuality():null,available:typeof player.getAvailableQualityLevels==='function'?player.getAvailableQualityLevels():null};}catch(ignore){}
            const samples=state.observation.samples;
            samples.push({second:samples.length,time:time,playerState:state.playerState,loadedFraction:Number.isFinite(loaded)?loaded:null});
            state.observation.advancedSeconds=time-samples[0].time;render();
            if(samples.length===observationSeconds+1){
                const pass=state.observation.advancedSeconds>=observationSeconds/2&&state.playerState===1;
                finish(pass?'PASS':'FAIL',pass?'Playback advanced at least half the observation duration':'Playback did not sustain sufficient time advancement');
                return;
            }
            observationTimer=setTimeout(sample,1000);
        }
        sample();
    }
    window.onYouTubeIframeAPIReady=function(){
        if(!active)return;
        event('api-ready');
        try{player=new window.YT.Player('player',{width:window.omniYouTubePlayerWidth||640,height:window.omniYouTubePlayerHeight||360,videoId:window.omniYouTubeVideoId||'M7lc1UVf-VE',
            playerVars:{autoplay:0,playsinline:1,origin:location.origin},events:{
                onReady:function(){if(!active)return;clearTimeout(readyTimer);readyTimer=null;ready=true;button.disabled=false;state.phase='waiting-user';result('embed ready',true,'playback not tested');event('onReady');if(automatic)requestPlay(false);},
                onStateChange:function(e){if(!active)return;state.playerState=e.data;event('onStateChange',e.data);if(e.data===1){clearTimeout(playTimer);playTimer=null;if(state.playback!=='playing')result('embed playing event',true,'event only; visual/audio unverified');state.playback='playing';state.phase='playing';render();observePlayback();}},
                onError:function(e){if(!active)return;event('onError',e.data);fail('embed error',e.data);},
                onAutoplayBlocked:function(){if(!active)return;clearTimeout(playTimer);playTimer=null;state.phase='waiting-user';state.playback='blocked';result('playback blocked',false,null);event('onAutoplayBlocked');finish('AUTOPLAY_BLOCKED','Browser or provider blocked automatic playback');}
            }});}catch(ignore){fail('player construction failed');}
    };
    function initialize(){
        if(document.readyState!=='complete')return {outcome:'not-ready'};
        if(state.phase!=='idle')return {outcome:'already-started'};
        if(location.protocol!=='http:'&&location.protocol!=='https:')return {outcome:'http-required'};
        active=true;state.phase='initializing';if(automatic)totalTimer=setTimeout(function(){finish('TIMEOUT','No playback result within '+totalSeconds+' seconds');},totalSeconds*1000);document.getElementById('initialize').disabled=true;
        readyTimer=setTimeout(function(){fail('embed readiness timeout');},30000);
        if(window.YT&&window.YT.Player)window.onYouTubeIframeAPIReady();
        else{script=document.createElement('script');script.src='https://www.youtube.com/iframe_api';script.async=true;script.onerror=function(){fail('API script load failed');};document.head.appendChild(script);}
        render();return {outcome:'initializing'};
    }
    function requestPlay(user){
        if(!active||!ready||playRequested)return;
        playRequested=true;clearTimeout(playTimer);state.phase='play-requested';state.playback='pending';event(user?'user-play':'selftest-play-request');
        playTimer=setTimeout(function(){fail('playback start timeout');},30000);
        try{player.playVideo();}catch(ignore){fail('play request failed');}
    };
    button.onclick=function(e){if(e&&e.isTrusted===true)requestPlay(true);};
    document.getElementById('initialize').onclick=initialize;
    document.getElementById('stop').onclick=function(){state.phase='stopped';cleanup();render();};
    window.addEventListener('pagehide',cleanup);
    window.omniStartMediaTest=initialize; // Automatic playback only when the explicit selftest option was set before loading.
    window.omniYouTubeDiagnostic={snapshot:function(){return JSON.parse(JSON.stringify(state));}};
    render();
})();
