// node --test addons/tests   (the new add-ons against the loader rules in OmniAddonsCore.h: parseManifest/readSetting limits)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..','bundled');
for(const id of['omni-resume-videos','omni-reader-view','omni-page-outline','omni-video-fit','omni-recipe-mode','omni-form-saver','omni-site-redirects','omni-search-blocklist','omni-unlock-select','omni-video-speed','omni-yt-chapters','omni-twitch-comfort','omni-image-gallery','omni-sticky-hide','omni-auto-scroll','omni-reading-ruler','omni-same-tab','omni-scroll-memory','omni-readable-font','omni-clear-links','omni-break-reminder','omni-yt-captions'])test(id+' manifest passes the loader checks',()=>{
  const dir=path.join(ROOT,id),raw=fs.readFileSync(path.join(dir,'manifest.json'),'utf8'),m=JSON.parse(raw);
  a.ok(raw.length<=64*1024);a.equal(m.manifest_version,1);a.equal(m.id,id);a.match(m.id,/^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/);
  for(const[k,max]of[['name',60],['version',24],['licence',60],['description',300],['source',300]])if(k in m||k!=='source'){a.equal(typeof m[k],'string');a.ok(m[k].length<=max,k)}
  a.match(m.source,/^https:\/\//);a.ok(['document_start','document_end','document_idle'].includes(m.run_at));
  a.ok(m.matches.length>0&&m.matches.length<=32&&m.excludes.length<=32);
  for(const p of[...m.matches,...m.excludes])a.match(p,/^(<all_urls>|(\*|https?):\/\/(\*|(\*\.)?[a-z0-9.-]+)\/.*)$/);
  for(const k of['all_frames','default_on','private_safe','quick_switch','live_toggle'])a.equal(typeof m[k],'boolean',k);
  a.ok(['user','author'].includes(m.css_level));a.deepEqual(m.hosts,[]);
  a.ok(m.js.length+m.css.length>0&&m.js.length<=8&&m.css.length<=8);
  let js=0,css=0;for(const f of m.js){a.match(f,/^[A-Za-z0-9._\/-]+\.js$/);const n=fs.statSync(path.join(dir,f)).size;a.ok(n<=1024*1024);js+=n}
  for(const f of m.css){a.match(f,/^[A-Za-z0-9._\/-]+\.css$/);css+=fs.statSync(path.join(dir,f)).size}
  a.ok(js<=2*1024*1024&&css<=512*1024);
  const keys=new Set();for(const s of m.settings||[]){a.match(s.key,/^[A-Za-z0-9_]{1,40}$/);a.ok(!keys.has(s.key));keys.add(s.key);a.ok(s.label.length<=80);
    if(s.type==='bool')a.equal(typeof s.default,'boolean');
    else if(s.type==='choice'){a.ok(s.choices.length>0&&s.choices.length<=16&&s.choices.includes(s.default));if(s.labels)a.equal(s.labels.length,s.choices.length)}
    else a.fail('unexpected setting type '+s.type)}
  a.ok(fs.existsSync(path.join(dir,'LICENSE'))&&fs.existsSync(path.join(dir,'SOURCES.md')));
});
test('resume add-on never runs in private tabs and leaves YouTube alone',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(ROOT,'omni-resume-videos','manifest.json'),'utf8'));
  a.equal(m.private_safe,false);a.ok(m.excludes.includes('*://*.youtube.com/*'));
});
