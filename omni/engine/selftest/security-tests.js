window.runOmniSecurityTests = async test => {
    const origin='http://192.0.2.20:8765';
    await test('security: cross-origin fetch is unreadable',async()=>{
        let rejected=false;try{await fetch(origin+'/data');}catch(e){rejected=e instanceof TypeError;}
        if(!rejected)throw Error('Cross-origin fetch was readable');return true;
    });
    await test('security: no-cors response stays opaque',async()=>{
        const response=await fetch(origin+'/data',{mode:'no-cors'});
        if(response.type!=='opaque'||response.status!==0||(await response.text())!=='')throw Error('Opaque response exposed data');return true;
    });
    await test('security: webpage cannot fetch console files',async()=>{
        let rejected=false;try{await fetch('file:///data/omni/controller-style.txt');}catch(e){rejected=e instanceof TypeError;}
        if(!rejected)throw Error('Webpage could fetch a local file');return true;
    });
    const frameCheck=path=>new Promise((resolve,reject)=>{
        const frame=document.createElement('iframe');frame.hidden=true;
        let messageSeen=false;
        const listener=e=>{if(e.source===frame.contentWindow&&e.origin===origin&&e.data==='omni-fixture-script')messageSeen=true;};
        addEventListener('message',listener);
        const finish=()=>{removeEventListener('message',listener);frame.remove();};
        const timer=setTimeout(()=>{finish();reject(Error('Fixture timeout'));},4000);
        frame.onload=()=>setTimeout(()=>{
            let originBlocked=false;
            try{void frame.contentWindow.document.body;}catch(e){originBlocked=e.name==='SecurityError';}
            clearTimeout(timer);finish();resolve({originBlocked,messageSeen});
        },250);
        frame.src=origin+path;document.body.append(frame);
    });
    await test('security: cross-origin iframe DOM isolation',async()=>{
        const result=await frameCheck('/frame');
        if(!result.originBlocked||!result.messageSeen)throw Error(JSON.stringify(result));return true;
    });
    await test('security: CSP blocks inline script',async()=>{
        const result=await frameCheck('/csp');
        if(!result.originBlocked||result.messageSeen)throw Error(JSON.stringify(result));return true;
    });
};
