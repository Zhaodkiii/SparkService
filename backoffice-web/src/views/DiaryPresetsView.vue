<template>
  <section class="presets">
    <h2>预设手帐</h2>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div class="columns">
      <aside>
        <h3>系列</h3>
        <button @click="newSeries">新增系列</button>
        <div v-for="s in series" :key="s.id"><button @click="chooseSeries(s.id)">{{ s.title }}</button></div>
        <button v-if="seriesID" @click="deleteSeries">删除系列</button>
      </aside>
      <main>
        <div v-if="seriesID"><button @click="newBook">新增手帐</button></div>
        <div class="books">
          <button v-for="b in books" :key="b.id" @click="chooseBook(b)"><img v-if="b.cover_url" :src="b.cover_url" :alt="b.title" style="height:100px;display:block" loading="lazy" />{{ b.title }} · {{ b.page_count }} 页 {{ b.active ? '' : '（已下架）' }}</button>
        </div>
        <template v-if="book">
          <h3>{{ book.title }} · 修订 {{ book.revision }}</h3>
          <div class="actions">
            <button @click="rename">改名</button>
            <button @click="publish">保存并发布</button>
            <button @click="archive">下架</button>
            <button @click="restore">历史版本回滚</button>
            <label>上传整本 <input type="file" accept=".zip" @change="upload($event, 'book')" :disabled="!!uploadClient" /></label>
            <label>新增单页（末尾）<input type="file" accept=".zip" @change="upload($event, 'page')" :disabled="!!uploadClient" /></label>
          </div>
          <p>支持完整 .diarypreset.zip，自动校验后直接发布。刷新后重新选择同一文件可恢复上传。</p>
          <div v-if="uploadStatus"><progress :value="progress" max="1" /> {{ uploadStatus }}
            <button v-if="uploadClient" @click="pauseUpload">暂停上传</button>
            <button v-if="paused" @click="resumeUpload">继续上传</button>
          </div>
          <div class="pages">
            <article v-for="(p, index) in pages" :key="p.id" draggable="true" @dragstart="drag = index" @dragover.prevent @drop="move(drag, index)">
              <img :src="p.thumbnail" :alt="p.title" loading="lazy" />
              <p>{{ index + 1 }}. {{ p.title }} {{ cover === p.id ? '（封面）' : '' }}</p>
              <button @click="move(index, index - 1)" :disabled="index === 0">前移</button>
              <button @click="move(index, index + 1)" :disabled="index === pages.length - 1">后移</button>
              <button @click="cover = p.id">设为封面</button>
              <button @click="renamePage(p)">修改页标题</button><button @click="remove(index)">删除单页</button>
            </article>
          </div>
        </template>
      </main>
    </div>
  </section>
</template>
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import OSS from 'ali-oss';
import http from '../api/http';
const base = '/api/admin/v1/diary-presets/';
interface Series { id: number; title: string }
interface Book { id: string; title: string; revision: number; active: boolean; cover_url?: string; page_count: number }
interface Page { id: string; title: string; thumbnail: string }
const series = ref<Series[]>([]), books = ref<Book[]>([]), pages = ref<Page[]>([]);
const seriesID = ref<number>(), book = ref<Book>(), cover = ref(''), drag = ref(0), error = ref('');
const progress = ref(0), uploadStatus = ref(''), paused = ref(false);
let uploadClient: OSS | undefined, checkpoint: any, source: File | undefined, sessionID = '', key = '', poll: ReturnType<typeof setTimeout> | undefined;
async function run(fn: () => Promise<void>) { error.value = ''; try { await fn(); } catch (e) { error.value = e instanceof Error ? e.message : String(e); } }
async function load() { series.value = (await http.get(base + 'series/')).data; }
async function chooseSeries(id: number) { await run(async () => { seriesID.value = id; book.value = undefined; books.value = (await http.get(base + 'templates/', { params: { series: id } })).data; }); }
async function chooseBook(b: Book) { await run(async () => { book.value = b; const data = (await http.get(base + `templates/${b.id}/pages/`)).data; pages.value = data.pages; cover.value = data.cover; book.value.revision = data.revision; }); }
async function newSeries() { const title = prompt('系列名称'); if (!title) return; const slug = prompt('系列标识（英文字母、数字、连字符）'); if (!slug) return; await run(async () => { await http.post(base+'series/', { title, slug }); await load(); }); }
async function deleteSeries() { if (!confirm('删除当前空系列？')) return; await run(async () => { await http.delete(base+`series/${seriesID.value}/`); seriesID.value=undefined; books.value=[]; book.value=undefined; await load(); }); }
async function newBook() { const title = prompt('手帐名称'); if (!title) return; await run(async () => { await http.post(base+'templates/', { title, series: seriesID.value }); await chooseSeries(seriesID.value!); }); }
async function rename() { const title = prompt('名称', book.value?.title); if (!title) return; await run(async () => { book.value = (await http.patch(base+`templates/${book.value!.id}/`, { title, revision:book.value!.revision })).data; }); }
function move(from: number, to: number) { if (from < 0 || to < 0 || to >= pages.value.length) return; const item = pages.value.splice(from, 1)[0]!; pages.value.splice(to, 0, item); }
function renamePage(p: Page) { const title=prompt('页面标题',p.title); if(title?.trim()) p.title=title.trim(); }
function remove(index: number) { if (!confirm('从下一版本移除此页？')) return; const p = pages.value.splice(index,1)[0]; if (p?.id === cover.value) cover.value = pages.value[0]?.id ?? ''; }
async function publish() { await run(async () => { const id=book.value!.id; book.value=(await http.put(base+`templates/${id}/pages/`, { revision:book.value!.revision, page_ids:pages.value.map(p=>p.id), cover_page_id:cover.value, titles:Object.fromEntries(pages.value.map(p=>[p.id,p.title])) })).data; book.value=(await http.post(base+`templates/${id}/publish/`, { revision:book.value!.revision })).data; await chooseBook(book.value!); }); }
async function archive() { if (!confirm('下架此手帐？')) return; await run(async () => { await http.delete(base+`templates/${book.value!.id}/`, {data:{revision:book.value!.revision}}); await chooseSeries(seriesID.value!); }); }
async function restore() { await run(async () => { const list=(await http.get(base+`templates/${book.value!.id}/versions/`)).data; const version=Number(prompt('可用历史版本：'+list.map((v:any)=>v.number).join(', '))); if (!version) return; book.value=(await http.post(base+`templates/${book.value!.id}/rollback/`, {revision:book.value!.revision,version})).data; await chooseBook(book.value!); }); }
const checkpointKey = 'diary-preset-upload-checkpoint';
function saveCheckpoint() {
  if (!source) return;
  const safe = checkpoint ? { ...checkpoint, file: undefined } : undefined;
  localStorage.setItem(checkpointKey, JSON.stringify({ sessionID, key, checkpoint: safe,
    name: source.name, size: source.size, modified: source.lastModified, template: book.value?.id }));
}
async function upload(event: Event, mode: string) { const input=event.target as HTMLInputElement; source=input.files?.[0]; if (!source) return;
const saved = JSON.parse(localStorage.getItem(checkpointKey) || 'null');
if (saved && saved.template === book.value?.id && saved.name === source.name && saved.size === source.size && saved.modified === source.lastModified && confirm('发现此文件未完成的上传，继续？')) {
  sessionID=saved.sessionID; key=saved.key; checkpoint=saved.checkpoint; await resumeUpload(); return;
}
checkpoint=undefined; progress.value=0; await run(async()=>{ const data=(await http.post(base+'uploads/', {template:book.value!.id,revision:book.value!.revision,mode,size:source!.size})).data; sessionID=data.id; key=data.credentials.key; uploadClient=new OSS({...data.credentials,refreshSTSToken:async()=>{ const c=(await http.post(base+`uploads/${sessionID}/refresh/`)).data; return c; },refreshSTSTokenInterval:300000}); await send(); }); }
async function send() { if (!source || !uploadClient) return; paused.value=false; uploadStatus.value='正在直传 OSS'; try { await uploadClient.multipartUpload(key,source,{checkpoint,headers:{'x-oss-object-acl':'private'},partSize:8*1024*1024,parallel:3,progress:async(p,c)=>{progress.value=p;checkpoint=c;saveCheckpoint();}}); await http.post(base+`uploads/${sessionID}/complete/`); localStorage.removeItem(checkpointKey); uploadClient=undefined; uploadStatus.value='上传完成，云端正在校验'; await status(); } catch(e) { if (!paused.value) { uploadClient=undefined; throw e; } } }
function pauseUpload(){ paused.value=true; uploadClient?.cancel(); uploadStatus.value='已暂停'; }
async function resumeUpload(){ await run(async()=>{ const c=(await http.post(base+`uploads/${sessionID}/refresh/`)).data; uploadClient=new OSS(c); await send(); }); }
async function status(){ await run(async()=>{const data=(await http.get(base+`uploads/${sessionID}/`)).data; uploadStatus.value=data.error || ({queued:'等待云端处理',processing:'云端校验中',published:'发布成功'} as Record<string,string>)[data.status] || data.status; if(['queued','processing'].includes(data.status)) poll=setTimeout(status,3000); else if(data.status==='published' && book.value) await chooseBook(book.value); }); }
onMounted(()=>run(load));
onUnmounted(()=>{if(poll)clearTimeout(poll);uploadClient?.cancel();});
</script>
<style scoped>
.presets{padding:24px}.columns{display:flex;gap:24px}.columns aside{min-width:160px}.columns main{flex:1}.books,.actions{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.pages{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}.pages article{padding:12px;border:1px solid #ddd;border-radius:12px}.pages img{width:100%;height:190px;object-fit:contain}button{margin:4px;padding:6px 12px;cursor:pointer}.error{color:#b42318}input[type=file]{max-width:210px}
</style>
