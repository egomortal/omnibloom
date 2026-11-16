// node --test addons/tests   (Site redirects add-on: the pure URL mapping, and runtime.js in a fake page)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const DIR=path.join(__dirname,'..','bundled','omni-site-redirects'),C=require(path.join(DIR,'core.js'));
const ALL={reddit:true,shorts:true,amp:true};

// ---------------------------------------------------------------- (a) Reddit
test('reddit: www, new and bare reddit.com go to old.reddit.com with path, query and fragment kept',()=>{
  a.equal(C.reddit('https://www.reddit.com/r/ps5/comments/abc/title/?sort=new#c1'),'https://old.reddit.com/r/ps5/comments/abc/title/?sort=new#c1');
  a.equal(C.reddit('https://new.reddit.com/r/all/'),'https://old.reddit.com/r/all/');
  a.equal(C.reddit('https://reddit.com/'),'https://old.reddit.com/');
  a.equal(C.reddit('http://www.reddit.com/r/x'),'https://old.reddit.com/r/x','plain http is upgraded');
  a.equal(C.reddit('https://WWW.Reddit.COM/r/X'),'https://old.reddit.com/r/X','host case ignored, path case kept');
  a.equal(C.reddit('https://www.reddit.com/r/a%20b/?q=%E2%9C%93&x=1%262'),'https://old.reddit.com/r/a%20b/?q=%E2%9C%93&x=1%262','encoding kept as is');
  a.equal(C.reddit('https://www.reddit.com/search/?q=a+b#'),'https://old.reddit.com/search/?q=a+b');
});
test('reddit: look-alikes, other subdomains, ports, userinfo, other schemes and new-only pages are left alone',()=>{
  for(const u of['https://old.reddit.com/r/x','https://www.reddit.com.evil.com/r/x','https://evilreddit.com/r/x','https://www.reddit.co/r/x',
    'https://evil.com/www.reddit.com/r/x','https://evil.com/?u=https://www.reddit.com/','https://www.reddit.com@evil.com/r/x','https://user:pw@www.reddit.com/r/x',
    'https://www.reddit.com:8443/r/x','https://www.reddit.com./r/x','ftp://www.reddit.com/r/x','javascript:alert(1)//www.reddit.com','https://m.reddit.com/r/x',
    'https://i.reddit.com/r/x','https://www.reddit.com/media?url=x','https://www.reddit.com/settings/','https://www.reddit.com/login','https://www.reddit.com/LOGIN/',
    'https://www.reddit.com/submit?title=x','https://www.reddit.com/api/vote','https://www.reddit.com/svc/shreddit/x','https://www.reddit.com/chat','',null,undefined,42,'not a url'])
    a.equal(C.reddit(u),null,String(u));
  a.equal(C.reddit('https://www.reddit.com/r/login'),'https://old.reddit.com/r/login','only top-level account paths are skipped');
  a.equal(C.reddit('https://www.reddit.com/'+'x'.repeat(9000)),null,'over-long address');
});

// ---------------------------------------------------------------- (b) YouTube Shorts
test('shorts: /shorts/<id> becomes /watch?v=<id> on the same YouTube host',()=>{
  a.equal(C.shorts('https://www.youtube.com/shorts/dQw4w9WgXcQ'),'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  a.equal(C.shorts('https://www.youtube.com/shorts/dQw4w9WgXcQ/'),'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  a.equal(C.shorts('https://m.youtube.com/shorts/a-b_C1234xy'),'https://m.youtube.com/watch?v=a-b_C1234xy');
  a.equal(C.shorts('http://youtube.com/shorts/dQw4w9WgXcQ'),'https://youtube.com/watch?v=dQw4w9WgXcQ');
  a.equal(C.shorts('https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share&t=5#x'),'https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share&t=5#x');
  a.equal(C.shorts('https://www.youtube.com/shorts/dQw4w9WgXcQ?v=EVILEVILEVI&t=1'),'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1','a second v is dropped');
  a.equal(C.shorts('https://WWW.YOUTUBE.COM/shorts/dQw4w9WgXcQ'),'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
});
test('shorts: bad ids, other paths and look-alike hosts are left alone',()=>{
  for(const u of['https://www.youtube.com.evil.com/shorts/dQw4w9WgXcQ','https://youtube.com.evil.com/shorts/dQw4w9WgXcQ','https://evilyoutube.com/shorts/dQw4w9WgXcQ',
    'https://www.youtube.com@evil.com/shorts/dQw4w9WgXcQ','https://evil.com/www.youtube.com/shorts/dQw4w9WgXcQ','https://music.youtube.com/shorts/dQw4w9WgXcQ',
    'https://youtu.be/shorts/dQw4w9WgXcQ','https://www.youtube-nocookie.com/shorts/dQw4w9WgXcQ','https://www.youtube.com:444/shorts/dQw4w9WgXcQ',
    'https://www.youtube.com/shorts/','https://www.youtube.com/shorts','https://www.youtube.com/shorts/short','https://www.youtube.com/shorts/dQw4w9WgXcQQ',
    'https://www.youtube.com/shorts/dQw4w9WgX%63Q','https://www.youtube.com/shorts/dQw4w9WgXc%3F','https://www.youtube.com/shorts/dQw4w9WgXcQ/extra',
    'https://www.youtube.com/SHORTS/dQw4w9WgXcQ','https://www.youtube.com/watch?v=dQw4w9WgXcQ','https://www.youtube.com/@chan/shorts',
    'https://www.youtube.com/feed/shorts','https://www.youtube.com/x/shorts/dQw4w9WgXcQ','data:text/html,/shorts/dQw4w9WgXcQ'])
    a.equal(C.shorts(u),null,u);
});

// ---------------------------------------------------------------- (c1) Google AMP viewer
test('google amp: /amp/s/<url> opens https://<url>, Google viewer parameters dropped',()=>{
  a.equal(C.googleAmp('https://www.google.com/amp/s/www.example.com/news/story.amp.html'),'https://www.example.com/news/story.amp.html');
  a.equal(C.googleAmp('https://google.com/amp/s/example.co.uk/amp/123'),'https://example.co.uk/amp/123');
  a.equal(C.googleAmp('http://www.google.com/amp/s/example.com/a'),'https://example.com/a','always https');
  a.equal(C.googleAmp('https://www.google.com/amp/s/example.com/a?usqp=mq331AQKKAFQArABIIACAw%3D%3D&id=7#top'),'https://example.com/a?id=7#top');
  a.equal(C.googleAmp('https://www.google.com/amp/s/example.com%2Fstory%3Fid%3D1'),'https://example.com/story?id=1','fully encoded address decoded once');
  a.equal(C.googleAmp('https://www.google.com/amp/s/example.com/a%2Fb'),'https://example.com/a%2Fb','a normal path is not decoded');
  a.equal(C.googleAmp('https://www.google.com/amp/s/EXAMPLE.com/a'),'https://example.com/a');
});
test('google amp: look-alikes, unsafe inner addresses and other paths are left alone',()=>{
  for(const u of['https://www.google.com.evil.com/amp/s/example.com/a','https://evil.com/amp/s/example.com/a','https://www.google.co.uk/amp/s/example.com/a',
    'https://www.google.com/amp/example.com/a','https://www.google.com/amp/s/','https://www.google.com/amp/s','https://www.google.com/search?q=/amp/s/example.com',
    'https://www.google.com/amp/s//evil.com/a','https://www.google.com/amp/s/user@evil.com/a','https://www.google.com/amp/s/example.com@evil.com/a',
    'https://www.google.com/amp/s/localhost/a','https://www.google.com/amp/s/router.localhost/a','https://www.google.com/amp/s/192.168.0.1/a','https://www.google.com/amp/s/example/a',
    'https://www.google.com/amp/s/example.com:8080/a','https://www.google.com/amp/s/www.google.com/amp/s/example.com/a','https://www.google.com/amp/s/news.google.co.uk/x',
    'https://www.google.com/amp/s/%65xample.com/a','https://www.google.com/amp/s/example.com%2F%ZZ','https://www.google.com/amp/s/javascript:alert(1)',
    'https://www.google.com/amp/s/%2F%2Fevil.com%2Fa','https://www.google.com:8443/amp/s/example.com/a'])
    a.equal(C.googleAmp(u),null,u);
});

// ---------------------------------------------------------------- (c2) AMP canonical
test('registrable domain: common suffixes, shared hosting and IPs',()=>{
  a.equal(C.registrable('www.example.com'),'example.com');a.equal(C.registrable('amp.news.example.com'),'example.com');
  a.equal(C.registrable('www.bbc.co.uk'),'bbc.co.uk');a.equal(C.registrable('co.uk'),null);a.equal(C.registrable('abc.net.au'),'abc.net.au');
  a.equal(C.registrable('alice.github.io'),'alice.github.io');a.equal(C.registrable('github.io'),null);a.equal(C.registrable('bucket.s3.amazonaws.com'),'bucket.s3.amazonaws.com');
  a.equal(C.registrable('example.uk'),'example.uk');a.equal(C.registrable('10.0.0.1'),'10.0.0.1');a.equal(C.registrable('localhost'),null);
  a.equal(C.registrable('example.com.'),null);a.equal(C.registrable('a..b.com'),null);a.equal(C.registrable(''),null);a.equal(C.registrable(null),null);
  a.equal(C.sameSite('amp.example.com','www.example.com'),true);a.equal(C.sameSite('alice.github.io','bob.github.io'),false);
  a.equal(C.sameSite('example.com.evil.com','example.com'),false);a.equal(C.sameSite('evil-example.com','example.com'),false);
});
test('canonical: same registrable domain, relative hrefs resolved, fragment carried over',()=>{
  a.equal(C.canonical('https://www.example.com/amp/story','https://www.example.com/story'),'https://www.example.com/story');
  a.equal(C.canonical('https://amp.example.com/story','https://www.example.com/story?id=1'),'https://www.example.com/story?id=1');
  a.equal(C.canonical('https://www.example.com/story/amp/#comments','../'),'https://www.example.com/story/#comments');
  a.equal(C.canonical('https://www.example.com/a.amp#x','/a#y'),'https://www.example.com/a#y','the canonical fragment wins');
  a.equal(C.canonical('http://www.example.com/amp/a','https://www.example.com/a'),'https://www.example.com/a','upgrade is fine');
  a.equal(C.canonical('https://m.bbc.co.uk/news/amp/1','https://www.bbc.co.uk/news/1'),'https://www.bbc.co.uk/news/1');
  a.equal(C.canonical('https://www.example.com/amp/a',' https://www.example.com/a '),'https://www.example.com/a');
});
test('canonical: other sites, downgrades, self links, loops and junk are refused',()=>{
  const P='https://www.example.com/amp/story';
  for(const[c,why]of[['https://evil.com/story','other site'],['https://www.example.com.evil.com/story','look-alike'],['https://example.co/story','other TLD'],
    ['http://www.example.com/story','https to http downgrade'],[P,'itself'],[P+'#top','itself with a fragment'],['https://www.example.com:8443/story','other port'],
    ['javascript:alert(1)','script'],['data:text/html,x','data'],['//evil.com/story','scheme-relative to another site'],['https://u:p@www.example.com/s','userinfo'],
    ['',''],[null,'null'],[undefined,'undefined']])
    a.equal(C.canonical(P,c),null,why);
  a.equal(C.canonical('https://alice.github.io/amp/a','https://bob.github.io/a'),null,'shared hosting tenants differ');
  a.equal(C.canonical('https://www.bbc.co.uk/amp/a','https://www.other.co.uk/a'),null);
  a.equal(C.canonical('ftp://www.example.com/amp/a','https://www.example.com/a'),null);
  a.equal(C.canonical('https://www.example.com/amp/story','https://www.example.com/story','https://www.example.com/story'),null,'came from the canonical: stay');
  a.equal(C.canonical('https://amp.example.com/story','https://www.example.com/story','https://www.example.com/'),null,'cross-origin referrer cut to the canonical origin');
  a.equal(C.canonical('https://www.example.com/amp/story','https://www.example.com/story','https://www.example.com/'),'https://www.example.com/story','same-origin home page referrer is a full URL');
  a.equal(C.canonical('https://www.example.com/amp/story','https://www.example.com/story','https://news.other.com/x'),'https://www.example.com/story');
});

// ---------------------------------------------------------------- rule selection, loops, flags
test('forUrl: each rule only when its setting is on; everything off by default',()=>{
  const r='https://www.reddit.com/r/x',s='https://www.youtube.com/shorts/dQw4w9WgXcQ',g='https://www.google.com/amp/s/example.com/a';
  for(const u of[r,s,g]){a.equal(C.forUrl(u),null);a.equal(C.forUrl(u,{}),null)}
  a.deepEqual(C.forUrl(r,{reddit:true}),{rule:'reddit',to:'https://old.reddit.com/r/x'});a.equal(C.forUrl(r,{shorts:true,amp:true}),null);
  a.deepEqual(C.forUrl(s,{shorts:true}),{rule:'shorts',to:'https://www.youtube.com/watch?v=dQw4w9WgXcQ'});a.equal(C.forUrl(s,{reddit:true,amp:true}),null);
  a.deepEqual(C.forUrl(g,{amp:true}),{rule:'amp',to:'https://example.com/a'});a.equal(C.forUrl(g,{reddit:true,shorts:true}),null);
});
test('never loops: every redirect target is a fixed point of the address rules',()=>{
  for(const u of['https://www.reddit.com/r/x?a=1#b','https://new.reddit.com/','https://www.youtube.com/shorts/dQw4w9WgXcQ?t=3','https://m.youtube.com/shorts/dQw4w9WgXcQ',
    'https://www.google.com/amp/s/www.reddit.com/r/x','https://www.google.com/amp/s/www.youtube.com/shorts/dQw4w9WgXcQ','https://www.google.com/amp/s/example.com/a']){
    const first=C.forUrl(u,ALL);a.ok(first,u);
    // a google AMP link to reddit/youtube is one more (separate) navigation at most, then nothing
    const second=C.forUrl(first.to,ALL);if(second){a.notEqual(second.rule,'amp');a.equal(C.forUrl(second.to,ALL),null,second.to)}}
  a.equal(C.forUrl('https://old.reddit.com/r/x',ALL),null);a.equal(C.forUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ',ALL),null);
});
test('only fresh navigations: reload and back/forward are left alone',()=>{
  a.equal(C.freshNavigation('navigate'),true);a.equal(C.freshNavigation(undefined),true);a.equal(C.freshNavigation(0),true);
  a.equal(C.freshNavigation('reload'),false);a.equal(C.freshNavigation('back_forward'),false);a.equal(C.freshNavigation('prerender'),false);a.equal(C.freshNavigation(2),false);
});
test('per-tab flags: remembered without the fragment, bounded, junk tolerated',()=>{
  let raw=null;a.equal(C.flagged(raw,'https://www.reddit.com/r/x'),false);
  raw=C.addFlag(raw,'https://www.reddit.com/r/x#c');a.equal(C.flagged(raw,'https://www.reddit.com/r/x'),true);a.equal(C.flagged(raw,'https://www.reddit.com/r/y'),false);
  a.equal(C.flagged(raw,'https://www.reddit.com/r/x?a=1'),false,'query is part of the address');
  for(let i=0;i<100;i++)raw=C.addFlag(raw,'https://www.reddit.com/r/'+i);a.equal(C.readFlags(raw).length,C.MAX_FLAGS);a.equal(C.flagged(raw,'https://www.reddit.com/r/99'),true);
  a.equal(C.flagged(raw,'https://www.reddit.com/r/x'),false,'oldest dropped');
  raw=C.addFlag(raw,'https://www.reddit.com/r/99');a.equal(C.readFlags(raw).filter(x=>x.endsWith('/r/99')).length,1,'no duplicates');
  for(const bad of['{','{"a":1}','"x"','[1,null,{}]','null'])a.deepEqual(C.readFlags(bad),[],bad);
});

// ---------------------------------------------------------------- runtime.js in a fake page
function fakePage(o={}){
  const settings=Object.assign({reddit:false,shorts:false,amp:false},o.settings),hooks={},replaced=[],session=new Map(o.session||[]),listeners={};
  const api={id:'omni-site-redirects',top:o.top!==false,active:o.active!==false,settings:{get:k=>settings[k]},onEnable:f=>hooks.enable=f,onDisable:f=>hooks.disable=f,onSettings:f=>hooks.settings=f};
  const loc={href:o.href,replace(u){replaced.push(u)}};
  const root={attrs:new Set(o.amp?['amp']:[]),hasAttribute(k){return this.attrs.has(k)}};
  const doc={readyState:o.readyState||'interactive',documentElement:root,referrer:o.referrer||'',
    querySelector(sel){if(!/canonical/.test(sel)||o.canonical==null)return null;return{getAttribute:()=>o.canonical}},
    addEventListener(t,f){(listeners[t]=listeners[t]||[]).push(f)},removeEventListener(t,f){listeners[t]=(listeners[t]||[]).filter(x=>x!==f)}};
  const win={omniAddon:api,document:doc,location:loc,URL,URLSearchParams,
    performance:{getEntriesByType:()=>[{type:o.nav||'navigate'}]},
    sessionStorage:{getItem:k=>session.has(k)?session.get(k):null,setItem:(k,v)=>{if(o.storageThrows)throw new Error('denied');session.set(k,String(v))}}};
  win.window=win;win.globalThis=win;const ctx=vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(DIR,'core.js'),'utf8'),ctx);
  return{settings,hooks,replaced,session,loc,doc,win,
    run(){vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),ctx)},
    fire(t){for(const f of[...(listeners[t]||[])])f()},listeners:t=>(listeners[t]||[]).length,diag:()=>win.OmniRedirectsDiagnostics()};
}
test('runtime: nothing happens with every rule off (the default)',()=>{
  for(const href of['https://www.reddit.com/r/x','https://www.youtube.com/shorts/dQw4w9WgXcQ','https://www.google.com/amp/s/example.com/a']){
    const p=fakePage({href});p.run();a.deepEqual(p.replaced,[]);a.equal(p.session.size,0)}
  const p=fakePage({href:'https://www.example.com/amp/a',amp:true,canonical:'https://www.example.com/a'});p.run();a.deepEqual(p.replaced,[]);
});
test('runtime: one location.replace, the source flagged, and a later visit to it (Back) stays put',()=>{
  const p=fakePage({href:'https://www.reddit.com/r/x?a=1#c',settings:{reddit:true}});p.run();
  a.deepEqual(p.replaced,['https://old.reddit.com/r/x?a=1#c']);a.equal(p.diag().redirected,true);
  a.equal(C.flagged(p.session.get(C.FLAG_KEY),'https://www.reddit.com/r/x?a=1'),true);
  const back=fakePage({href:'https://www.reddit.com/r/x?a=1',settings:{reddit:true},session:[...p.session]});back.run();a.deepEqual(back.replaced,[]);
  const other=fakePage({href:'https://www.reddit.com/r/y',settings:{reddit:true},session:[...p.session]});other.run();a.equal(other.replaced.length,1);
});
test('runtime: reload and back/forward navigations, and frames, are never redirected',()=>{
  for(const nav of['reload','back_forward']){const p=fakePage({href:'https://www.reddit.com/r/x',nav,settings:{reddit:true}});p.run();a.deepEqual(p.replaced,[],nav)}
  const f=fakePage({href:'https://www.reddit.com/r/x',top:false,settings:{reddit:true}});f.run();a.deepEqual(f.replaced,[]);
});
test('runtime: no storage (blocked) still redirects only once per page',()=>{
  const p=fakePage({href:'https://www.youtube.com/shorts/dQw4w9WgXcQ',storageThrows:true,settings:{shorts:true}});p.run();
  a.equal(p.replaced.length,1);p.fire('yt-navigate-finish');p.hooks.disable();p.hooks.enable();a.equal(p.replaced.length,1);
});
test('runtime: YouTube in-page navigation to a Short is redirected once; a Back into a flagged Short is not',()=>{
  const p=fakePage({href:'https://www.youtube.com/',settings:{shorts:true}});p.run();a.deepEqual(p.replaced,[]);
  p.loc.href='https://www.youtube.com/watch?v=aaaaaaaaaaa';p.fire('yt-navigate-finish');a.deepEqual(p.replaced,[]);
  p.loc.href='https://www.youtube.com/shorts/dQw4w9WgXcQ';p.fire('yt-navigate-finish');p.fire('yt-navigate-finish');
  a.deepEqual(p.replaced,['https://www.youtube.com/watch?v=dQw4w9WgXcQ']);
  const q=fakePage({href:'https://www.youtube.com/',settings:{shorts:true},session:[...p.session]});q.run();
  q.loc.href='https://www.youtube.com/shorts/dQw4w9WgXcQ';q.fire('yt-navigate-finish');a.deepEqual(q.replaced,[],'flag from this tab');
  q.hooks.disable();a.equal(q.listeners('yt-navigate-finish'),0,'listener removed when switched off');
});
test('runtime: AMP canonical after the head is parsed, only on pages that say they are AMP',()=>{
  const p=fakePage({href:'https://www.example.com/amp/a',readyState:'loading',amp:true,canonical:'/a',settings:{amp:true}});p.run();
  a.deepEqual(p.replaced,[]);p.fire('DOMContentLoaded');a.deepEqual(p.replaced,['https://www.example.com/a']);
  const notAmp=fakePage({href:'https://www.example.com/example',canonical:'/other',settings:{amp:true}});notAmp.run();a.deepEqual(notAmp.replaced,[]);
  const away=fakePage({href:'https://www.example.com/amp/a',amp:true,canonical:'https://evil.com/a',settings:{amp:true}});away.run();a.deepEqual(away.replaced,[]);
  const fromCanon=fakePage({href:'https://www.example.com/amp/a',amp:true,canonical:'/a',referrer:'https://www.example.com/a',settings:{amp:true}});fromCanon.run();a.deepEqual(fromCanon.replaced,[]);
  const g=fakePage({href:'https://www.google.com/amp/s/example.com/a',settings:{amp:true}});g.run();a.deepEqual(g.replaced,['https://example.com/a']);
});
test('manifest: opt-in rules, specific matches only, never in private tabs',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));
  a.equal(m.default_on,false);a.equal(m.private_safe,false);a.equal(m.all_frames,false);a.equal(m.run_at,'document_start');
  a.ok(!m.matches.includes('<all_urls>')&&!m.matches.includes('*://*/*'));
  a.deepEqual(m.settings.map(s=>[s.key,s.type,s.default]),[['reddit','bool',false],['shorts','bool',false],['amp','bool',false]]);
});
