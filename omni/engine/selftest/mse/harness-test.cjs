const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/smoke.js','utf8');
async function scenario(MediaSource,fetch) {
  let paused=0,detached=0,loaded=0;
  const video={pause(){paused++},removeAttribute(){detached++},load(){loaded++}};
  const button={},report={};
  const context=vm.createContext({window:{},document:{getElementById:id=>({video,run:button,result:report})[id]},MediaSource,fetch,URL,Uint8Array,setTimeout,clearTimeout});
  vm.runInContext(source,context);
  await button.onclick();
  return {result:context.window.omniMSEResult,paused,detached,loaded,disabled:button.disabled};
}
(async()=>{
  const unsupported=await scenario(undefined,()=>{throw Error('must not fetch')});
  assert.equal(unsupported.result.status,'UNSUPPORTED');assert.equal(unsupported.disabled,false);
  const failed=await scenario(class{},async()=>({ok:false,status:404}));
  assert.equal(failed.result.status,'FAIL');assert.match(failed.result.error,/404/);
  assert.deepEqual([failed.paused,failed.detached,failed.loaded],[1,1,1]);assert.equal(failed.disabled,false);
  console.log('PASS harness unsupported detection and fetch-error cleanup (mock DOM; not browser MSE validation)');
})().catch(e=>{console.error(e);process.exitCode=1});
