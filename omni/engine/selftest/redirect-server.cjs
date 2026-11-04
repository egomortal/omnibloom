// Temporary LAN-only redirect fixture; exits automatically after two minutes.
const http=require('http');
const server=http.createServer((req,res)=>{
  const name=req.url==='/blocked-redirect'?'blocked':req.url==='/allowed-redirect'?'excepted':null;
  if(!name){res.writeHead(404);res.end();return;}
  console.log('Redirect fixture:',req.url);
  res.writeHead(302,{Location:`http://127.0.0.1:8080/fs/data/omni/ublock-test/${name}.js`,'Cache-Control':'no-store'});
  res.end();
});
server.listen(8765,'192.0.2.20',()=>console.log('Omni redirect fixture listening'));
setTimeout(()=>server.close(),120000);
