const {test}=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const ts=require('../node_modules/typescript')
function moduleAt(name){const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',name),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInNewContext(code,{exports,Promise,Map,Math,Error,Infinity});return exports}
test('image pool deduplicates, limits concurrency and retries failures',async()=>{
 const {createImagePool}=moduleAt('asset-cache.ts');let running=0,max=0,calls=0
 const pending=[];const pool=createImagePool(src=>{calls++;running++;max=Math.max(max,running);return new Promise((resolve,reject)=>pending.push({src,resolve:v=>{running--;resolve(v)},reject:e=>{running--;reject(e)}}))},()=>4,16,2)
 const a=pool.get('a'),same=pool.get('a'),b=pool.get('b'),c=pool.get('c');assert.equal(a,same);assert.equal(calls,2)
 pending[0].resolve({});pending[1].resolve({});await Promise.all([a,b]);await new Promise(setImmediate);assert.equal(calls,3);pending[2].resolve({});await c;assert.equal(max,2)
 const bad=pool.get('bad');pending[3].reject(Error('network'));await assert.rejects(bad);await new Promise(setImmediate);const retry=pool.get('bad');pending[4].resolve({});await retry;assert.equal(calls,5)
})
test('image pool releases oldest retained entries when over pixel budget',async()=>{
 const {createImagePool}=moduleAt('asset-cache.ts');let calls=0
 const pool=createImagePool(async()=>({id:++calls}),()=>8,8,1)
 await pool.get('one');await pool.get('two');await pool.get('one');assert.equal(calls,3)
})
test('fallback rectangle contains the complete irregular rotated outline',()=>{
 const {enclosingRectangle}=moduleAt('slot-geometry.ts')
 const angle=.23,c=Math.cos(angle),s=Math.sin(angle)
 const points=[[0,0],[90,-4],[100,10],[103,45],[92,55],[15,59],[-3,40]].map(([x,y])=>({x:x*c-y*s,y:x*s+y*c}))
 const quad=enclosingRectangle(points);assert.equal(quad.length,4)
 for(let i=0;i<4;i++){const a=quad[i],b=quad[(i+1)%4];for(const p of points)assert.ok((b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x)>=-1e-6)}
})
test('quad expansion covers torn borders beyond the four-corner fit',()=>{
 const {expandQuadToHull}=moduleAt('slot-geometry.ts'),quad=[{x:0,y:0},{x:100,y:0},{x:100,y:100},{x:0,y:100}],points=[...quad,{x:102,y:50}]
 const result=expandQuadToHull(quad,points);assert.ok(result[1].x>=102-1e-6)
})
test('layer categories inherit groups but explicit child semantics win',()=>{
 const {layerCategory,layerCategories}=moduleAt('layer-categories.ts')
 assert.equal(layerCategories.length,5)
 assert.equal(layerCategory({kind:'photo'},'paper'),'paper')
 assert.equal(layerCategory({kind:'photo',semanticKind:'photo'},'paper'),'photo')
 assert.equal(layerCategory({kind:'frame'}),'photo')
 assert.equal(layerCategory({kind:'object'}),undefined)
 assert.equal(layerCategory({kind:'sticker',semanticKind:'branding'},'illustration'),'branding')
 assert.equal(layerCategory({isLibraryBackground:true},'illustration'),'background')
})
test('v2 photo and frame objects survive hidden text parent, matching iOS import',()=>{
 const {visibleLayerIds}=moduleAt('layer-categories.ts')
 const objects={root:{layers:[{id:'caption-group',kind:'text',renderType:'group',contentID:'mixed'}]},mixed:{layers:[
  {id:'photo-group',kind:'photo',renderType:'group',contentID:'photo'},
  {id:'frame-group',kind:'photo',renderType:'group',contentID:'frame'},
  {id:'caption',kind:'text',renderType:'image',assetID:'text'},
  {id:'logo',kind:'branding',renderType:'image',assetID:'logo'}]},
 photo:{layers:[{id:'photo-slot',kind:'photo',renderType:'image',subcategory:'slot',assetID:'photo'}]},
 frame:{layers:[{id:'photo-frame',kind:'photo',renderType:'image',subcategory:'frame',assetID:'frame'}]}}
 assert.deepEqual(Array.from(visibleLayerIds(objects,'root',['text','paper','illustration'])),['photo-slot','photo-frame','logo'])
 assert.deepEqual(Array.from(visibleLayerIds(objects,'root',['photo'])),['caption','logo'])
 assert.deepEqual(Array.from(visibleLayerIds(objects,'root',[])),['photo-slot','photo-frame','caption','logo'])
})
function readerHarness(){
 const source=fs.readFileSync(path.join(__dirname,'../src/BookApp.vue'),'utf8').split('<script setup lang="ts">')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const exposed=source+'\n;globalThis.reader={active,index,busy,turn,hiddenCategories,filteredPages,filterBusy,navigate,toggleCategory,open};'
 const code=ts.transpileModule(exposed,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText
 let writes=0,calls=0;const timers=[];const context={ref:v=>({value:v}),computed:fn=>({get value(){return fn()}}),onMounted:()=>{},api:()=>{calls++;return new Promise(()=>{})},base:()=>'',saveDraft:async()=>{writes++},listDrafts:async()=>[],setTimeout:fn=>{timers.push(fn)},requestAnimationFrame:fn=>fn(),console,Map,Set,Promise,JSON,Date,Error}
 vm.runInNewContext(code,context);return {reader:context.reader,get writes(){return writes},get calls(){return calls},timers}
}
test('turning pages resets temporary filters and never waits for pending API',()=>{
 const h=readerHarness(),r=h.reader;r.active.value={id:'b',pages:[],units:[{rightPageID:'a'},{leftPageID:'b',rightPageID:'c'}],overrides:{},replacements:{}};r.hiddenCategories.value=['text'];r.filterBusy.value=true;r.filteredPages.value={a:'filtered'}
 r.navigate(1)
 assert.equal(r.index.value,1);assert.equal(r.active.value.lastIndex,1)
 assert.equal(r.hiddenCategories.value.length,0);assert.equal(r.filterBusy.value,false)
 assert.equal(r.busy.value,false);assert.ok(h.calls>0);assert.equal(r.turn.value,'next')
 h.timers[0]();assert.equal(r.turn.value,'')
})
test('restoring a temporary category does not write a draft',async()=>{
 const h=readerHarness(),r=h.reader;r.active.value={id:'b',pages:[],units:[],replacements:{}};r.hiddenCategories.value=['text']
 await r.toggleCategory('text');assert.equal(r.hiddenCategories.value.length,0);assert.equal(h.writes,0)
})
