// Checks that each of the 10 original universes shows its own launch art, and that nothing asks for the old
// emerald-core.png. Usage: node test-original-art.cjs <worker dir>   (needs Playwright with Chromium)
const fs=require('fs'),path=require('path'),http=require('http');
const pw=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const dir=path.resolve(process.argv[2]||path.join(__dirname,'../worker'));
const ids=['aurora','cosmic','arcade','solstice','metro','sakura','abyss','prism','atlas','cassette'];
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.json':'application/json','.woff2':'font/woff2'};
const wk=fs.readFileSync(path.join(dir,'worker.py'),'utf8');
const routes=[...wk.matchAll(/'(\/assets\/[^']+)': \('([^']+)'/g)].reduce((m,x)=>(m[x[1]]=x[2],m),{});
let failures=[],requested=[];
const server=http.createServer((req,res)=>{const u=new URL(req.url,'http://x').pathname;requested.push(u);let f=u==='/'?'index.html':routes[u];
 if(!f){res.writeHead(404).end();return}const p=path.join(dir,f);if(!fs.existsSync(p)){res.writeHead(404).end();return}
 res.setHeader('Content-Type',types[path.extname(p)]||'application/octet-stream');res.end(fs.readFileSync(p))});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 const b=await pw.chromium.launch();
 for(const id of ids){
  if(!routes[`/assets/art/${id}.webp`])failures.push(`${id}: no worker route`);
  const page=await b.newPage({viewport:{width:1920,height:1080}});requested=[];
  await page.goto(base+'/',{waitUntil:'domcontentloaded'});
  await page.evaluate(t=>document.body.setAttribute('data-theme',t),id);
  await page.evaluate(()=>{if(!document.querySelector('.hero-art')){const d=document.createElement('div');d.className='hero-art';document.body.appendChild(d)}});
  const bg=await page.evaluate(()=>getComputedStyle(document.querySelector('.hero-art')).backgroundImage);
  if(!bg.includes(`/assets/art/${id}.webp`))failures.push(`${id}: hero art is ${bg}`);
  await page.waitForTimeout(300);
  const other=requested.filter(u=>ids.some(o=>o!==id&&u.endsWith(`/assets/art/${o}.webp`)));
  if(other.length)failures.push(`${id}: also loaded ${other.join(', ')}`);
  if(requested.some(u=>u.includes('emerald-core')))failures.push(`${id}: requested emerald-core.png`);
  await page.close()}
 await b.close();server.close();
 console.log(JSON.stringify({checked:ids.length,failures},null,2));process.exitCode=failures.length?1:0})();
