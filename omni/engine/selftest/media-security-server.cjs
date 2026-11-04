// Local synthetic media fixtures; serves only the specified generated test clip.
const http = require('http');
const fs = require('fs');
const clip = fs.readFileSync(process.argv[2]);
const server = http.createServer((req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    const path = new URL(req.url, 'http://fixture.invalid').pathname;
    console.log('fixture request', path);
    if (path === '/video' || path === '/cors' || path === '/media-blocked.mp4') {
        if (path === '/cors') res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Content-Type', 'video/mp4');
        res.setHeader('Content-Length', clip.length);
        res.end(clip); return;
    }
    // Deliver a body byte so ports which defer response policy until first data
    // actually exercise the advertised-size check. Never allocate the claimed body.
    if (path === '/oversized') { res.writeHead(200, {'Content-Type':'video/mp4','Content-Length':33554433}); res.end('x'); return; }
    if (path === '/malformed') { res.writeHead(200, {'Content-Type':'video/mp4'}); res.end('invalid synthetic media'); return; }
    if (path === '/csp-page') {
        res.setHeader('Content-Security-Policy', "media-src 'none'");
        res.setHeader('Content-Type', 'text/html');
        res.end(`<!doctype html><video muted></video><script>const v=document.querySelector('video');v.onerror=()=>parent.postMessage({omniMediaCSP:true},'http://127.0.0.1:8080');v.onloadeddata=()=>parent.postMessage({omniMediaCSP:false},'http://127.0.0.1:8080');v.src='/video';</script>`);return;
    }
    if (path === '/redirect') {
        res.writeHead(302, {Location: 'http://192.0.2.10:8080/fs/data/omni/media-test.mp4'});
        res.end(); return;
    }
    if (path === '/page') {
        res.setHeader('Content-Type', 'text/html');
        res.end(`<!doctype html><video muted></video><script>
        const v=document.querySelector('video');
        v.onloadeddata=()=>{let blocked=false;try{const c=document.createElement('canvas');c.width=320;c.height=180;const x=c.getContext('2d');x.drawImage(v,0,0);x.getImageData(0,0,1,1);}catch(e){blocked=e.name==='SecurityError';}parent.postMessage({omniMediaRedirect:blocked},'http://127.0.0.1:8080');};
        v.onerror=()=>parent.postMessage({omniMediaRedirect:false,error:'load'},'http://127.0.0.1:8080');
        v.src='/redirect';</script>`); return;
    }
    res.writeHead(404); res.end();
});
server.listen(8766, '192.0.2.20', () => console.log('Media security fixtures ready'));
setTimeout(() => server.close(), 180000);
