<template>
 <div class="payments"><div class="heading"><div><h1>支付管理</h1><p>管理印制付款渠道、交易和原路退款</p></div><a-button @click="load" :loading="busy">刷新</a-button></div>
 <a-alert v-if="error" type="error" :message="error" show-icon closable @close="error=''" />
 <a-tabs v-model:activeKey="tab" @change="changeTab">
  <a-tab-pane v-if="capabilities.configure" key="channels" tab="支付渠道"><div class="cards"><a-card v-for="c in channels" :key="c.code" :title="name(c.code)">
   <a-tag :color="c.enabled?'green':'default'">{{c.enabled?'已启用':'未启用'}}</a-tag><p>生效版本：{{c.current_id??'未发布'}} · 未结束交易 {{c.pending_count}} 笔</p>
   <p>最新配置：{{c.draft?.checked_at?'格式检查通过':'待填写或检查'}} · {{c.draft?.environment==='sandbox'?'测试环境':'正式环境'}}</p>
   <a-space><a-button type="primary" @click="edit(c)">配置渠道</a-button><a-button @click="openControl(c)">运行设置</a-button></a-space>
  </a-card></div></a-tab-pane>
  <a-tab-pane v-if="capabilities.view" v-for="item in operationTabs" :key="item.key" :tab="item.title"><PaymentOperations v-if="tab===item.key" :kind="item.key" :access="capabilities" :refresh-key="refreshKey"/></a-tab-pane>
 </a-tabs>
 <a-drawer :open="!!editing" :title="`配置${name(editing?.code||'')}收款`" :width="760" :mask-closable="false" @close="closeEditor">
  <div v-if="editing" class="editor">
   <a-alert v-if="formError" type="error" :message="formError" show-icon />
   <a-alert :message="`连接环境：${serviceOrigin}。草稿仅保存在此服务，不会自动同步到其他服务器。`" type="info" show-icon />
   <a-steps size="small" :current="step" :items="[{title:'填写配置'},{title:'联调（可选）'},{title:'核对并启用'}]"/>
   <p class="muted">当前生效：{{editing.current_id ? '版本 '+editing.current_id : '尚未发布'}} · {{editing.enabled?'正在接收付款':'渠道关闭'}}。修改草稿不影响历史交易。</p>
   <a-form layout="vertical" class="config-form" :disabled="saving||testing">
    <h3>1. 应用与收款账户</h3>
    <a-form-item label="环境" required><a-select v-model:value="environment" :options="editing.code==='wechat'?[{value:'production',label:'正式'}]:[{value:'production',label:'正式'},{value:'sandbox',label:'沙箱（仅保存配置，不向用户开放）'}]" @change="environmentChanged"/><div class="muted">切换环境需重新填写该环境的密钥。</div></a-form-item>
    <a-form-item label="应用 AppID" required :validate-status="fieldErrors.APPID?'error':undefined" :help="fieldErrors.APPID||'在开放平台的应用详情中获取'"><a-input v-model:value="publicValues.APPID"/></a-form-item>
    <template v-if="editing.code==='wechat'">
     <a-form-item v-for="f in wxFields" :key="f.key" :label="f.title" required :validate-status="fieldErrors[f.key]?'error':undefined" :help="fieldErrors[f.key]"><a-input v-model:value="publicValues[f.key]"/></a-form-item>
    </template>
    <a-form-item v-else label="支付宝商家 PID" required :validate-status="fieldErrors.SELLER_ID?'error':undefined" :help="fieldErrors.SELLER_ID||'实际收款商家账号的 16 位身份 ID；与 AppID 不同'"><a-input v-model:value="publicValues.SELLER_ID"/></a-form-item>
    <a-form-item label="支付结果通知地址" required :validate-status="fieldErrors.NOTIFY_URL?'error':undefined" :help="fieldErrors.NOTIFY_URL||'支付宝/微信须可通过公网 HTTPS 访问；本地地址不能接收正式通知'"><a-input v-model:value="publicValues.NOTIFY_URL"/><a-space><a-button type="link" @click="publicValues.NOTIFY_URL=editing.suggested_callback">使用当前服务地址</a-button><a-button type="link" @click="copy(publicValues.NOTIFY_URL||'')">复制地址</a-button></a-space></a-form-item>
    <h3>2. 密钥材料</h3><p class="muted">支持直接粘贴平台提供的密钥字符串或完整 PEM，系统自动识别。密钥保存后不会回显。</p>
    <a-form-item v-for="f in secretFields" :key="f.key" :label="f.label" required :validate-status="fieldErrors[f.key]?'error':undefined" :help="fieldErrors[f.key]">
     <div class="material-status"><a-tag :color="material(f.key)?.valid?'green':material(f.key)?.configured?'orange':'default'">{{material(f.key)?.valid ? `已配置 · ${material(f.key)?.bits ? 'RSA '+material(f.key)?.bits+' 位' : '格式有效'}` : material(f.key)?.configured?'已保存 · 格式待修正':'尚未配置'}}</a-tag><a-button v-if="material(f.key)?.configured" type="link" @click="replacing[f.key]=!replacing[f.key];secretValues[f.key]=''">{{replacing[f.key]?'取消替换':'更换密钥'}}</a-button></div>
     <template v-if="!material(f.key)?.configured||replacing[f.key]"><a-textarea v-model:value="secretValues[f.key]" :rows="f.key==='API_V3_KEY'?2:4" :placeholder="f.hint" autocomplete="off" :spellcheck="false"/><div class="muted">{{f.hint}}</div></template>
    </a-form-item>
   </a-form>
   <h3>3. 联调验证（可选）</h3>
   <a-alert v-if="dirty" message="配置有未保存修改，请先保存并检查，再进行联调。" type="warning" show-icon/>
   <a-alert v-else-if="!editing.draft" message="先填写配置并保存，系统将逐项检查格式。" type="info" show-icon/>
   <template v-else><p>版本 {{editing.draft.id}} · {{editing.draft.checked_at?'本地格式检查通过':'待检查'}}。格式通过不代表商户权限或密钥配对已验证。</p>
    <PaymentProbePanel :tests="editing.draft.tests" :active="editing.draft.active_test" :version-id="editing.draft.id" :channel="name(editing.code)" :link="probeLink" :link-probe-id="probeID" :busy="testing||saving" :disabled="dirty" :device-enabled="canDeviceTest&&environment==='production'" :checked="!!editing.draft.checked_at" @create="createProbe" @refresh="refreshTests" @resume="showProbe" @close="probeAction($event,'close')" @query="probeAction($event,'query')" @restart="restartProbe" @copy="copy"/>
    <p><a-tag v-if="editing.draft.test_expired" color="blue">未支付签名到期：已验证</a-tag><a-tag :color="editing.draft.test_paid?'green':'default'">付款并退款：{{editing.draft.test_paid?'通过':'待验证'}}</a-tag><a-tag :color="editing.draft.test_closed?'green':'default'">取消并关单：{{editing.draft.test_closed?'通过':'待验证'}}</a-tag></p>
   </template>
   <h3>4. 核对并启用</h3><p class="muted">配置格式检查通过后可直接启用，联调为可选验证；沙箱不能用于正式收款。</p>
   <a-textarea :disabled="saving||testing" v-model:value="verifiedNote" :rows="2" placeholder="启用备注（选填，最多 1000 字），可记录验证结果或启用原因" :maxlength="1000"/>
   <h3>版本记录</h3><a-collapse><a-collapse-panel v-for="v in editing.versions" :key="v.id" :header="`版本 ${v.id} · ${date(v.created_at)}${v.id===editing.current_id?' · 生效':''}`"><p>{{v.actor}} · {{v.environment==='production'?'正式':'沙箱'}} · {{v.checked_at?'格式通过':'待检查'}}</p><div v-for="(value,key) in v.public" :key="key">{{fieldLabel(String(key))}}：{{value}}</div><p>{{v.verified_note||'暂无联调备注'}}</p></a-collapse-panel></a-collapse>
  </div>
  <template #footer><div class="editor-footer"><span class="muted">{{dirty?'有未保存修改':'配置已保存'}}{{noteDirty?' · 备注未提交':''}}</span><a-space><a-button @click="closeEditor">关闭</a-button><a-button type="primary" :loading="saving" @click="save">保存并检查</a-button><a-button :disabled="!canPublish" :loading="saving" @click="confirmPublish">核对并启用</a-button></a-space></div></template>
 </a-drawer>
 <a-modal :open="!!channelControl" title="渠道运行设置" :confirm-loading="saving" @ok="savePosition" @cancel="channelControl=null"><p>{{name(channelControl?.code||'')}} · {{channelControl?.enabled?'已启用':'已关闭'}}</p><a-form-item label="客户端显示顺序（数字越小越靠前）"><a-input-number v-model:value="position" :min="0" :max="100"/></a-form-item><a-popconfirm :title="`停用后停止新付款；${channelControl?.pending_count||0} 笔未结束交易仍继续处理。`" @confirm="disableChannel"><a-button danger :disabled="!channelControl?.enabled">停用渠道</a-button></a-popconfirm><a-alert v-if="controlError" type="error" :message="controlError"/></a-modal>

 </div>
</template>
<script setup lang="ts">
import PaymentOperations from '../components/print/PaymentOperations.vue';
import {useRoute} from 'vue-router';
import PaymentProbePanel from '../components/print/PaymentProbePanel.vue';
import {computed,onMounted,onBeforeUnmount,ref,watch} from 'vue';import {onBeforeRouteLeave} from 'vue-router';import {Modal,message} from 'ant-design-vue';import http from '../api/http';
interface Material{configured:boolean;valid:boolean;bits?:number}
interface Probe{id:string;state:string;created_at:string;expires_at:string;last_error:string;can_resume:boolean;expired:boolean}
interface Version{active_test?:Probe|null;materials:Record<string,Material>;tests:Probe[];test_paid:boolean;test_closed:boolean;test_expired?:boolean;id:number;environment:string;public:Record<string,string>;checked_at:string|null;actor:string;created_at:string;verified_note:string}
interface Channel{suggested_callback:string;code:string;enabled:boolean;position:number;revision:number;current_id:number|null;pending_count:number;draft:Version|null;versions:Version[]}
const route=useRoute();
const capabilities=ref({view:false,query:false,refund:false,configure:false,orders:false});
const operationTabs=[{key:'transactions',title:'支付交易'},{key:'refunds',title:'退款管理'},{key:'audit',title:'操作记录'}];
const refreshKey=ref(0);
const tab=ref('channels'),channels=ref<Channel[]>([]),busy=ref(false),error=ref(''),editing=ref<Channel|null>(null),formError=ref(''),saving=ref(false),environment=ref('production'),publicValues=ref<Record<string,string>>({}),secretValues=ref<Record<string,string>>({}),verifiedNote=ref(''),position=ref(0),baseline=ref('');
const fieldErrors=ref<Record<string,string>>({}),replacing=ref<Record<string,boolean>>({}),probeLink=ref(''),probeID=ref(''),testing=ref(false),channelControl=ref<Channel|null>(null),controlError=ref('');
const wxFields=[{key:'MCHID',title:'微信商户号'},{key:'SERIAL',title:'商户证书序列号'},{key:'PUBLIC_KEY_ID',title:'微信支付公钥 ID'}];
const serviceOrigin=(import.meta.env.VITE_API_BASE_URL||window.location.origin).replace(/\/+$/,'');
const canDeviceTest=serviceOrigin==='https://diary.dreamwhale.top';
const date=(s:string)=>new Date(s).toLocaleString('zh-CN',{hour12:false});
const base='/api/admin/v1/print/payments/';const name=(v:string)=>v==='wechat'?'微信支付':v==='alipay'?'支付宝':v;const explain=(e:unknown)=>e instanceof Error?e.message:'操作失败';
const fieldLabel=(k:string)=>({id:'支付 / 退款单号',order_id:'印制订单号',title:'作品',channel:'渠道',config_version:'配置版本',amount:'金额（分）',state:'状态',provider_id:'渠道流水号',created_at:'创建时间',paid_at:'支付时间',checked_at:'最近同步',expires_at:'到期时间',last_error:'异常',reason:'退款原因',attempt_id:'原支付单号'} as Record<string,string>)[k]||k;
const secretFields=computed(()=>[{key:'PRIVATE_KEY',label:editing.value?.code==='alipay'?'应用私钥':'商户私钥',hint:'在密钥工具生成并保管的私钥；不要填写应用公钥'},{key:'PUBLIC_KEY',label:editing.value?.code==='alipay'?'支付宝公钥':'微信支付公钥',hint:'从支付平台获取的验签公钥；支付宝页面上方的应用公钥不能填在这里'},...(editing.value?.code==='wechat'?[{key:'API_V3_KEY',label:'API v3 密钥',hint:'32 字节 API v3 密钥'}]:[])]);
const dirty=computed(()=>JSON.stringify([environment.value,publicValues.value])!==baseline.value||Object.values(secretValues.value).some(Boolean));
const noteDirty=computed(()=>verifiedNote.value!==(editing.value?.draft?.verified_note||''));
const material=(key:string)=>environment.value===editing.value?.draft?.environment?editing.value?.draft?.materials[key]:undefined;
const canPublish=computed(()=>!!editing.value?.draft?.checked_at&&!dirty.value&&!testing.value&&!saving.value&&environment.value==='production');
const step=computed(()=>!editing.value?.draft||dirty.value?0:editing.value.enabled?2:1);
async function load(){if(tab.value!=='channels'){refreshKey.value++;return}if(!capabilities.value.configure)return;busy.value=true;error.value='';try{channels.value=await http.get(base+'channels/') as unknown as Channel[]}catch(e){error.value=explain(e)}finally{busy.value=false}}
function changeTab(){error.value='';void load()}
watch(()=>route.query.section,()=>{const value=String(route.query.section||'');if(operationTabs.some(t=>t.key===value)&&capabilities.value.view)tab.value=value});

function edit(c:Channel){editing.value=JSON.parse(JSON.stringify(c));environment.value=c.draft?.environment||'production';publicValues.value={...c.draft?.public};secretValues.value={};replacing.value={};verifiedNote.value=c.draft?.verified_note||'';baseline.value=JSON.stringify([environment.value,publicValues.value]);formError.value='';fieldErrors.value={};probeLink.value='';probeID.value='';const active=c.draft?.active_test||c.draft?.tests.find(p=>p.can_resume);if(active?.can_resume)void showProbe(active.id)}
function closeEditor(){if(saving.value||testing.value)return;if(dirty.value||noteDirty.value)Modal.confirm({title:'放弃未提交的修改？',content:'包含配置、密钥和联调备注。',onOk:()=>{editing.value=null;secretValues.value={};probeLink.value=''}});else{editing.value=null;secretValues.value={};probeLink.value=''}}
function environmentChanged(){const reset=()=>{secretValues.value={};replacing.value={};fieldErrors.value={}};if(Object.values(secretValues.value).some(Boolean))Modal.confirm({title:'切换环境将清空尚未保存的密钥输入',onOk:reset,onCancel:()=>{environment.value=editing.value?.draft?.environment||'production'}});else reset()}
async function copy(text:string){try{await navigator.clipboard.writeText(text);message.success('已复制')}catch{message.error('复制失败，请手动复制')}}
function validateForm(){const errors:Record<string,string>={};for(const key of ['APPID','NOTIFY_URL',...(editing.value?.code==='wechat'?['MCHID','SERIAL','PUBLIC_KEY_ID']:['SELLER_ID'])])if(!publicValues.value[key]?.trim())errors[key]='此项必填';for(const f of secretFields.value)if(!material(f.key)?.configured&&!secretValues.value[f.key]?.trim())errors[f.key]='请填写此项';if(editing.value?.code==='alipay'){for(const key of ['APPID','SELLER_ID'])if(!/^\d{16}$/.test(publicValues.value[key]||''))errors[key]='应为 16 位数字'}try{const u=new URL(publicValues.value.NOTIFY_URL||'');if(u.protocol!=='https:'||['localhost','127.0.0.1'].includes(u.hostname))errors.NOTIFY_URL='请填写公网 HTTPS 回调地址'}catch{errors.NOTIFY_URL='请输入有效 HTTPS 地址'}fieldErrors.value=errors;return !Object.keys(errors).length}
async function save(){if(!editing.value||saving.value||testing.value||!validateForm())return;saving.value=true;formError.value='';try{const c=await http.post(base+'channels/',{code:editing.value.code,revision:editing.value.revision,action:'save',environment:environment.value,public:publicValues.value,secrets:secretValues.value}) as unknown as Channel;channels.value=channels.value.map(old=>old.code===c.code?c:old);const note=verifiedNote.value;edit(c);verifiedNote.value=note;message.success('配置已保存，格式检查通过')}catch(e){formError.value=explain(e);const fields=['APPID','SELLER_ID','NOTIFY_URL','PRIVATE_KEY','PUBLIC_KEY','API_V3_KEY'];for(const key of fields){const match=formError.value.match(new RegExp(key+'：([^；]+)'));if(match)fieldErrors.value[key]=match[1]||'请检查'}}finally{saving.value=false}}
async function refreshEditor(){if(!editing.value||dirty.value)return;const code=editing.value.code;const all=await http.get(base+'channels/') as unknown as Channel[];channels.value=all;const current=all.find(c=>c.code===code);if(current){if(current.draft?.id!==editing.value?.draft?.id)throw new Error('配置版本已被其他管理员更新，请关闭后重新打开配置');editing.value=current;if(!current.draft?.active_test?.can_resume&&!current.draft?.tests.some(p=>p.can_resume)){probeLink.value='';probeID.value=''}}}
async function refreshTests(){testing.value=true;formError.value='';try{await refreshEditor()}catch(e){formError.value=explain(e)}finally{testing.value=false}}
async function createProbe(){if(!editing.value?.draft||dirty.value)return;testing.value=true;formError.value='';try{const p=await http.post(base+'probes/',{action:'create',version_id:editing.value.draft.id}) as unknown as {id:string;link:string;expires_at:string};probeLink.value=p.link;probeID.value=p.id;await refreshEditor()}catch(e){formError.value=explain(e)}finally{testing.value=false}}
async function showProbe(id:string){if(testing.value||saving.value)return;testing.value=true;formError.value='';try{const p=await http.post(base+'probes/',{id,action:'link'}) as unknown as {id:string;link:string;expires_at:string};if(editing.value?.draft?.tests.some(p=>p.id===id)||editing.value?.draft?.active_test?.id===id){probeLink.value=p.link;probeID.value=p.id}}catch(e){probeLink.value='';formError.value=explain(e)}finally{testing.value=false}}
async function restartProbe(id:string){if(testing.value||saving.value||dirty.value)return;testing.value=true;formError.value='';try{await http.post(base+'probes/',{id,action:'close'});await refreshEditor();testing.value=false;await createProbe()}catch(e){formError.value=explain(e)}finally{testing.value=false}}
async function probeAction(id:string,action:string){if(testing.value||saving.value)return;testing.value=true;formError.value='';try{await http.post(base+'probes/',{id,action});await refreshEditor()}catch(e){formError.value=explain(e)}finally{testing.value=false}}
function confirmPublish(){if(!canPublish.value||!editing.value)return;const c=editing.value;const untested=!c.draft?.test_paid||!c.draft?.test_closed;Modal.confirm({title:untested?'尚未完成全部联调，确认直接启用？':'确认启用正式收款？',okText:'确认启用收款',cancelText:'返回检查',content:`${name(c.code)} · 版本 ${c.draft?.id} · AppID ${publicValues.value.APPID} · 商户 ${publicValues.value.SELLER_ID||publicValues.value.MCHID}。${untested?`付款与退款：${c.draft?.test_paid?'已验证':'未验证'}；取消关单：${c.draft?.test_closed?'已验证':'未验证'}。`:""}启用后客户端立即可以发起真实付款。`,onOk:async()=>{saving.value=true;try{const updated=await http.post(base+'channels/',{code:c.code,revision:c.revision,action:'publish',confirm_enable:true,version_id:c.draft?.id,verified_note:verifiedNote.value}) as unknown as Channel;channels.value=channels.value.map(old=>old.code===c.code?updated:old);edit(updated);message.success('渠道已启用')}catch(e){formError.value=explain(e);throw e}finally{saving.value=false}}})}
function openControl(c:Channel){channelControl.value=c;position.value=c.position;controlError.value=''}
async function controlAction(action:string){const c=channelControl.value;if(!c)return;saving.value=true;controlError.value='';try{const updated=await http.post(base+'channels/',{code:c.code,revision:c.revision,action,position:position.value}) as unknown as Channel;channels.value=channels.value.map(old=>old.code===c.code?updated:old);channelControl.value=updated;message.success('运行设置已更新')}catch(e){controlError.value=explain(e)}finally{saving.value=false}}
async function savePosition(){await controlAction('position');if(!controlError.value)channelControl.value=null}
async function disableChannel(){await controlAction('disable')}
function unload(e:BeforeUnloadEvent){if(editing.value&&(dirty.value||noteDirty.value)){e.preventDefault();e.returnValue=''}}
window.addEventListener('beforeunload',unload);onBeforeUnmount(()=>window.removeEventListener('beforeunload',unload));
onBeforeRouteLeave(()=>{if(!editing.value||(!dirty.value&&!noteDirty.value))return true;return new Promise<boolean>(resolve=>Modal.confirm({title:'离开并放弃未提交的修改？',onOk:()=>resolve(true),onCancel:()=>resolve(false)}))});
onMounted(async()=>{try{capabilities.value=await http.get(base+'access/') as unknown as typeof capabilities.value;const requested=String(route.query.section||'');tab.value=operationTabs.some(t=>t.key===requested)&&capabilities.value.view?requested:capabilities.value.view?'transactions':'channels';await load()}catch(e){error.value=explain(e)}});
</script>
<style scoped>.payments{padding:28px;background:white}.heading{display:flex;justify-content:space-between;align-items:center}.heading p,.muted{color:#758093}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}h1{margin:0}h3{margin-top:24px}.ant-table-wrapper{margin-top:18px}.editor{display:flex;flex-direction:column;gap:16px}.editor h3{margin:8px 0 0}.editor-footer{display:flex;justify-content:space-between;align-items:center;gap:12px}.material-status{display:flex;align-items:center;margin-bottom:8px}.probe{display:flex;align-items:center;gap:20px}.editor textarea{font-family:monospace}.config-form .muted{font-size:12px}</style>
