// Synthetic security fixtures only; no real accounts or private data.
const http=require('http');
const server=http.createServer((req,res)=>{
    res.setHeader('Cache-Control','no-store');
    if(req.url==='/data'){res.setHeader('Content-Type','text/plain');res.end('OMNI_SYNTHETIC_CROSS_ORIGIN_DATA');return;}
    if(req.url==='/frame' || req.url==='/csp'){
        res.setHeader('Content-Type','text/html');
        if(req.url==='/csp')res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'none'");
        res.end('<!doctype html><title>Omni security fixture</title><script>parent.postMessage("omni-fixture-script", "*")</script>');return;
    }
    res.writeHead(404);res.end();
});
server.listen(8765,'192.0.2.20',()=>console.log('Omni synthetic security fixtures listening'));
setTimeout(()=>server.close(),120000);
