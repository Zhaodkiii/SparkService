<template>
 <div class="print-console">
  <header class="heading"><div><h1>印制订单</h1><p class="muted">从印前审核到交付，处理每一本实物手帐。</p></div><a-space><a-button :loading="listBusy" @click="refreshAll">刷新</a-button><a-button @click="productsOpen=true">印制规格</a-button></a-space></header>
  <div class="queue-grid"><button v-for="item in queues" :key="item.key" class="queue" :class="{selected:state===item.key}" @click="filter(item.key)"><span>{{item.name}}</span><strong>{{counts[item.key]||0}}</strong><small>{{item.hint}}</small></button></div>
  <a-alert v-if="pageError" type="error" show-icon :message="pageError" class="gap" />
  <section class="orders-panel"><div class="filters"><a-input-search v-model:value="search" placeholder="订单号或作品名称" @search="filter(state)" allow-clear style="max-width:320px"/><a-select v-model:value="state" style="width:170px" @change="filter(state)"><a-select-option value="">全部订单</a-select-option><a-select-option v-for="(name,key) in states" :key="key" :value="key">{{name}}</a-select-option><a-select-option value="after_sale">售后待办</a-select-option><a-select-option value="exception">异常订单</a-select-option></a-select><span class="muted">共 {{total}} 单 · 每 30 秒同步</span></div>
   <a-table :data-source="orders" :columns="columns" row-key="id" :loading="listBusy" :pagination="false" :scroll="{x:1000}" :locale="{emptyText:pageError?'加载失败，请点击刷新重试':state?'当前队列没有订单':'暂无订单，用户提交后会显示在这里'}">
    <template #bodyCell="{column,record}">
     <template v-if="column.key==='book'"><a class="book-title" @click="openOrder(record.id)">{{record.title}}</a><div class="muted order-number">{{record.number}}</div><a-tag v-if="['open','processing'].includes(record.after_sale_state)" color="orange">售后{{label(record.after_sale_state)}}</a-tag></template>
     <template v-else-if="column.key==='spec'"><strong>{{record.spec.title}} · {{record.quantity}} 份</strong><div class="muted">{{record.spec.width_mm}} × {{record.spec.height_mm}} mm</div><div class="muted">{{record.page_count}} 面内页 / 每份 {{record.sheets_per_copy}} 张纸</div></template>
     <template v-else-if="column.key==='amount'">{{record.total_fen===0?'免费':'¥'+money(record.total_fen)}}<div class="muted">{{label(record.payment_state)}}</div></template>
     <template v-else-if="column.key==='status'"><a-tag :color="color(record.state)">{{status(record)}}</a-tag><div v-if="record.state!=='draft'" class="muted">{{label(record.file_state)}}</div><a-tag v-if="record.refund_state==='exception'" color="red">退款异常</a-tag></template>
     <template v-else-if="column.key==='date'"><div>{{elapsed(record.stage_started_at)}}</div><div class="muted">下单 {{date(record.created_at)}}</div></template>
     <template v-else-if="column.key==='action'"><a-button @click="openOrder(record.id)">{{record.state==='awaiting_review'?'去审核':record.state==='ready_to_ship'?'去发货':'查看处理'}}</a-button></template>
    </template>
   </a-table><div class="pagination"><a-pagination :current="offset/30+1" :total="total" :page-size="30" :show-size-changer="false" @change="changePage" /></div>
  </section>
  <a-drawer :open="!!selectedID" title="订单处理" width="min(1080px, 100vw)" @close="closeOrder">
   <template #extra><a-button :loading="detailBusy" @click="loadDetail()">刷新详情</a-button></template>
   <a-alert v-if="detailError" type="error" show-icon :message="detailError" class="gap" />
   <a-spin :spinning="detailBusy&&!order"><template v-if="order">
    <div class="heading"><div><h2>{{order.title}}</h2><a-typography-text copyable class="muted">{{order.number}}</a-typography-text></div><a-tag :color="color(order.state)">{{status(order)}}</a-tag></div>
    <a-alert v-if="order.exception_reason" type="warning" show-icon :message="order.state==='needs_revision'?'等待用户修改后重提':'制作已暂停'" :description="order.exception_reason" class="gap" />
    <a-alert v-if="order.production_error" type="error" show-icon :message="order.production_error" class="gap" />
    <div v-if="order.after_sale_state" class="service-box"><h3>售后 · {{label(order.after_sale_state)}}</h3><p>{{order.after_sale_message}}</p><p v-if="order.after_sale_resolution">处理结果：{{order.after_sale_resolution}}</p><a-space><a-button v-for="a in saleActions" :key="a" @click="prepareAction(a)">{{actions[a]}}</a-button></a-space></div>
    <div v-if="order.refund_state" class="service-box"><strong>退款：{{order.refund_state==='exception'?'异常，需要核对':label(order.payment_state)}}</strong><p>{{order.refund_reason}}</p><a-button v-if="order.allowed_actions.includes('refresh_refund')" @click="prepareAction('refresh_refund')">重新核对退款</a-button></div>
    <a-tabs v-model:active-key="detailTab">
     <a-tab-pane key="production" tab="生产与审核">
      <a-descriptions bordered :column="2" size="small">
       <a-descriptions-item label="成品规格">{{order.spec.title}} · {{order.spec.width_mm}} × {{order.spec.height_mm}} mm</a-descriptions-item><a-descriptions-item label="印制份数"><strong>{{order.quantity}} 份</strong></a-descriptions-item>
       <a-descriptions-item label="内页">{{order.page_count}} 面 · {{order.spec.duplex?'双面':'单面'}} · 每份 {{order.sheets_per_copy}} 张纸</a-descriptions-item><a-descriptions-item label="封面">正封面＋封底，另计 2 面</a-descriptions-item>
       <a-descriptions-item label="纸张">{{order.spec.paper}}</a-descriptions-item><a-descriptions-item label="装订">{{order.spec.binding}}</a-descriptions-item>
       <a-descriptions-item label="交付方式">无出血 · 内页按阅读顺序</a-descriptions-item><a-descriptions-item label="制作周期">{{order.spec.lead_time||'未设置'}}</a-descriptions-item>
      </a-descriptions>
      <div class="heading file-toolbar"><div><h3>当前生产稿</h3><span class="muted">{{label(order.file_state)}} · 第 {{order.production_number}} 次提交</span></div><a-space wrap v-if="order.can_download"><a-button :loading="fileBusy" @click="preview('cover')">预览封面 / 封底</a-button><a-button :loading="fileBusy" @click="preview('interior')">预览内页</a-button><a-button type="primary" :loading="fileBusy" @click="downloadFile('interior')">下载内页 PDF</a-button><a-button @click="downloadFile('cover')">下载封面 PDF</a-button><a-button @click="downloadInstructions">下载生产说明</a-button></a-space></div>
      <p class="muted">文件已由客户端检查并上传，请预览并人工审核。预览和下载直接连接文件存储。</p>
      <div class="gap"><a-tag v-for="check in order.checks.filter(x=>!x.includes('等待人工'))" :key="check">{{check}}</a-tag></div>
      <div v-if="previewURL" class="preview"><div class="preview-heading"><strong>{{previewRole==='cover'?'正封面与封底（按此顺序）':'内页（阅读顺序）'}}</strong><a-button size="small" :loading="fileBusy" @click="preview(previewRole,true)">重新加载</a-button></div><iframe :src="previewURL" title="生产稿 PDF 预览" /><p class="muted">未显示 PDF 时，可<a :href="previewURL" target="_blank" rel="noopener noreferrer">在独立窗口预览</a>。授权链接到期会自动更新。</p></div>
     </a-tab-pane>
     <a-tab-pane key="delivery" tab="收货与物流"><div class="address"><strong>{{order.address.name}} · {{order.address.phone}}</strong><p>{{order.address.region}} {{order.address.detail}}</p><a-button size="small" @click="copyAddress">复制收货信息</a-button></div>
      <a-empty v-if="!order.shipments.length" description="尚未登记发货" />
      <div v-for="s in order.shipments" :key="s.id" class="shipment"><a-tag>{{s.kind==='reship'?'补寄':'首次发货'}}</a-tag><strong>{{s.carrier}}</strong><a-typography-text copyable>{{s.tracking_number}}</a-typography-text><span class="muted">{{date(s.created_at)}}</span><a-button v-if="order.allowed_actions.includes('correct_shipment')" size="small" @click="prepareAction('correct_shipment',s)">更正</a-button></div>
      <a-space class="gap"><a-button v-for="a in deliveryActions" :key="a" @click="prepareAction(a)">{{actions[a]}}</a-button></a-space>
      <a-descriptions bordered :column="1"><a-descriptions-item label="订单金额">{{order.total_fen===0?'免费':'¥'+money(order.total_fen)}} · {{label(order.payment_state)}}</a-descriptions-item><a-descriptions-item label="购买与售后约定">{{order.spec.terms}}</a-descriptions-item></a-descriptions>
     </a-tab-pane>
     <a-tab-pane key="history" tab="操作记录"><a-timeline><a-timeline-item v-for="e in [...order.events].reverse()" :key="e.id"><strong>{{e.message||e.action}}</strong><p v-if="e.details.checklist" class="muted">已检查：{{e.details.checklist.join('；')}}</p><div class="muted">{{e.actor}} · {{date(e.created_at)}}</div></a-timeline-item></a-timeline></a-tab-pane>
    </a-tabs>
   </template></a-spin>
   <template #footer><div v-if="order" class="heading footer"><span class="muted">{{elapsed(order.stage_started_at)}}</span><a-space wrap><a-dropdown v-if="secondaryActions.length"><a-button :disabled="actionBusy">更多操作</a-button><template #overlay><a-menu><a-menu-item v-for="a in secondaryActions" :key="a" :danger="['cancel','refund'].includes(a)" @click="prepareAction(a)">{{actions[a]}}</a-menu-item></a-menu></template></a-dropdown><a-button v-if="primaryAction" type="primary" :disabled="actionBusy" @click="prepareAction(primaryAction)">{{actions[primaryAction]}}</a-button></a-space></div></template>
  </a-drawer>
  <a-modal v-model:open="actionOpen" :title="actions[currentAction]" :confirm-loading="actionBusy" :mask-closable="!actionBusy" :closable="!actionBusy" :cancel-button-props="{disabled:actionBusy}" :ok-button-props="{danger:['cancel','refund'].includes(currentAction),disabled:!actionValid}" ok-text="确认提交" cancel-text="返回" @ok="submitAction">
   <template v-if="order"><div class="confirm-order"><strong>{{order.title}}</strong><div class="muted">{{order.number}}</div><p>{{order.spec.title}} · {{order.quantity}} 份 · {{order.page_count}} 面内页</p></div>
    <a-alert v-if="actionError" type="error" show-icon :message="actionError" class="gap" />
    <p v-if="currentAction==='needs_revision'">用户可在原作品的“装订成册”页面重新提交，保留订单与付款信息。重提须保持规格、份数及内页面数。</p>
    <p v-if="currentAction==='refund'">全额退款 ¥{{money(order.total_fen)}}。未交寄订单将取消；请确认已停止线下制作。</p>
    <p v-if="currentAction==='cancel'">{{order.payment_state==='paid'?'取消后申请原路退款，到账以微信结果为准。':'此订单取消后不再制作。'}}</p>
    <p v-if="currentAction==='refresh_refund'">查询原退款单的最新结果；异常仍需按微信返回结果处理，不会重复创建退款。</p>
    <a-checkbox-group v-if="Object.keys(actionChecks).length" v-model:value="checked" class="checklist"><a-checkbox v-for="(name,key) in actionChecks" :key="key" :value="key">{{name}}</a-checkbox></a-checkbox-group>
    <a-form layout="vertical"><template v-if="isShipping"><div class="address"><strong>{{order.address.name}} · {{order.address.phone}}</strong><p>{{order.address.region}} {{order.address.detail}}</p></div><a-form-item label="快递公司" required><a-input v-model:value="carrier" :maxlength="80" /></a-form-item><a-form-item label="快递单号" required :validate-status="tracking&&!trackingValid?'error':undefined" :help="tracking&&!trackingValid?'请输入 5–80 位字母、数字或连字符':undefined"><a-input v-model:value="tracking" :maxlength="80" /></a-form-item><a-checkbox v-model:checked="addressConfirmed">已核对收货信息与实际交寄单据</a-checkbox></template>
     <a-form-item v-if="needsNote" :label="currentAction==='resolve_after_sale'?'处理结果（用户可见）':'具体原因或核实说明（用户可见）'" required><a-textarea v-model:value="actionMessage" :maxlength="1000" show-count :rows="4" :placeholder="currentAction==='needs_revision'?'请注明需要修改的页码、问题和修改要求':'请填写具体说明'" /></a-form-item>
    </a-form>
   </template>
  </a-modal>
  <ProductDrawer :open="productsOpen" @close="productsOpen=false" />
 </div>
</template>
<script setup lang="ts">
import {computed,ref,onMounted,onUnmounted} from 'vue';
import {message} from 'ant-design-vue';
import http,{ApiError} from '../api/http';
import ProductDrawer from '../components/print/ProductDrawer.vue';
import {type Order,type Shipment,states,actions,label,money,date,status,color,errorText} from '../components/print/types';
const base='/api/admin/v1/print/';
const orders=ref<Order[]>([]),order=ref<Order>(),selectedID=ref(''),search=ref(''),state=ref(''),offset=ref(0),total=ref(0),counts=ref<Record<string,number>>({});
const pageError=ref(''),detailError=ref(''),actionError=ref(''),listBusy=ref(false),detailBusy=ref(false),actionBusy=ref(false),fileBusy=ref(false),productsOpen=ref(false),detailTab=ref('production');
const queues=[{key:'awaiting_review',name:'待审核',hint:'检查封面与内页'},{key:'queued',name:'待制作',hint:'下载后开始制作'},{key:'producing',name:'制作中',hint:'完成后逐项质检'},{key:'ready_to_ship',name:'待发货',hint:'核对收件与物流'},{key:'after_sale',name:'售后待办',hint:'及时回应用户'},{key:'exception',name:'异常订单',hint:'重提、暂停或失败'}];
const columns=[{title:'作品 / 订单号',key:'book',width:240},{title:'规格与份数',key:'spec',width:230},{title:'费用',key:'amount',width:100},{title:'状态',key:'status',width:140},{title:'当前阶段 / 下单时间',key:'date',width:215},{title:'处理',key:'action',width:110}];
function elapsed(s:string){const h=Math.max(0,Math.floor((Date.now()-Date.parse(s))/3600000));return h<1?'本阶段不足 1 小时':h<24?`本阶段 ${h} 小时`:`本阶段 ${Math.floor(h/24)} 天 ${h%24} 小时`}
let listSequence=0,detailSequence=0;
async function loadList(){const seq=++listSequence;listBusy.value=true;try{const data=await http.get(base+'orders/',{params:{offset:offset.value,state:state.value,search:search.value}}) as unknown as {results:Order[];total:number;counts:Record<string,number>};if(seq!==listSequence)return;orders.value=data.results;total.value=data.total;counts.value=data.counts;pageError.value=''}catch(e){if(seq===listSequence)pageError.value=errorText(e)}finally{if(seq===listSequence)listBusy.value=false}}
function filter(value:string){state.value=value;offset.value=0;void loadList()}
function changePage(p:number){offset.value=(p-1)*30;void loadList()}
async function loadDetail(force=false){if(actionBusy.value&&!force)return;const id=selectedID.value;if(!id)return;const seq=++detailSequence;detailBusy.value=true;try{const value=await http.get(base+`orders/${id}/`) as unknown as Order;if(seq!==detailSequence||id!==selectedID.value)return;if(order.value?.production_id!==value.production_id||!value.can_download)clearFiles();order.value=value;detailError.value=''}catch(e){if(seq===detailSequence)detailError.value=errorText(e)}finally{if(seq===detailSequence)detailBusy.value=false}}
function openOrder(id:string){selectedID.value=id;order.value=undefined;detailError.value='';detailTab.value='production';clearFiles();void loadDetail()}
function closeOrder(){if(actionBusy.value)return;selectedID.value='';order.value=undefined;detailSequence++;detailBusy.value=false;clearFiles()}
async function refreshAll(){await Promise.allSettled([loadList(),loadDetail()])}
const primaryAction=computed(()=>['approve','start','finish','ship','resume'].find(a=>order.value?.allowed_actions.includes(a))||'');
const saleActions=computed(()=>order.value?.allowed_actions.filter(a=>['accept_after_sale','resolve_after_sale'].includes(a))||[]);
const deliveryActions=computed(()=>order.value?.allowed_actions.filter(a=>['reship','complete'].includes(a))||[]);
const secondaryActions=computed(()=>order.value?.allowed_actions.filter(a=>a!==primaryAction.value&&!['accept_after_sale','resolve_after_sale','refresh_refund','correct_shipment','reship','complete'].includes(a))||[]);
const actionOpen=ref(false),currentAction=ref(''),actionMessage=ref(''),checked=ref<string[]>([]),carrier=ref(''),tracking=ref(''),addressConfirmed=ref(false),shipmentID=ref<number>();
let actionKey='',actionRevision=0,actionProduction='';
const actionChecks=computed(()=>order.value?.checklists[currentAction.value]||{});
const isShipping=computed(()=>['ship','reship','correct_shipment'].includes(currentAction.value));
const needsNote=computed(()=>['needs_revision','refund','pause','resume','reprint','reship','correct_shipment','complete','resolve_after_sale'].includes(currentAction.value));
const trackingValid=computed(()=>/^[A-Za-z0-9-]{5,80}$/.test(tracking.value.trim()));
const actionValid=computed(()=>!!order.value?.allowed_actions.includes(currentAction.value)&&(!needsNote.value||!!actionMessage.value.trim())&&(!isShipping.value||(!!carrier.value.trim()&&trackingValid.value&&addressConfirmed.value))&&Object.keys(actionChecks.value).every(k=>checked.value.includes(k)));
function prepareAction(a:string,s?:Shipment){if(!order.value||actionBusy.value)return;currentAction.value=a;actionKey=crypto.randomUUID();actionRevision=order.value.revision;actionProduction=order.value.production_id;actionMessage.value='';checked.value=[];carrier.value=s?.carrier||'';tracking.value=s?.tracking_number||'';shipmentID.value=s?.id;addressConfirmed.value=false;actionError.value='';actionOpen.value=true}
async function submitAction(){if(!order.value||!actionValid.value||actionBusy.value)return;actionBusy.value=true;detailSequence++;detailBusy.value=false;actionError.value='';try{order.value=await http.post(base+`orders/${order.value.id}/`,{key:actionKey,revision:actionRevision,production_id:actionProduction,action:currentAction.value,message:actionMessage.value.trim(),checklist:checked.value,carrier:carrier.value.trim(),tracking_number:tracking.value.trim(),address_confirmed:addressConfirmed.value,shipment_id:shipmentID.value}) as unknown as Order;actionOpen.value=false;clearFiles();message.success('订单已更新');await loadList()}catch(e){actionError.value=errorText(e);if(e instanceof ApiError&&e.status===409){await loadDetail(true);actionRevision=order.value?.revision||0;actionProduction=order.value?.production_id||'';actionKey=crypto.randomUUID();checked.value=[];addressConfirmed.value=false;actionError.value+='；已刷新详情，请重新核对后提交'}else if(e instanceof ApiError&&e.status&&e.status<500){actionKey=crypto.randomUUID()}else{await loadDetail(true);actionOpen.value=false;detailError.value='请求结果暂不明确，已尝试刷新订单。请核对操作记录和物流记录后再决定是否重试。'}}finally{actionBusy.value=false}}
interface DownloadLinks {production_id:string;expires_at:string;files:Record<string,string>}
let links:DownloadLinks|undefined;
const previewURL=ref(''),previewRole=ref('cover');
function clearFiles(){links=undefined;previewURL.value=''}
async function getFiles(force=false){if(!order.value?.can_download)throw new Error('此订单当前不可下载');const id=order.value.id,production=order.value.production_id;if(!force&&links?.production_id===production&&Date.parse(links.expires_at)>Date.now()+15000)return links;const value=await http.post(base+`orders/${id}/downloads/`) as unknown as DownloadLinks;if(selectedID.value!==id||order.value?.production_id!==production||!order.value.can_download)throw new Error('订单已切换，请重新操作');links=value;return value}
async function preview(role:string,force=false){if(fileBusy.value)return;fileBusy.value=true;detailError.value='';try{const value=await getFiles(force);previewRole.value=role;previewURL.value=value.files[role]||''}catch(e){detailError.value=errorText(e)}finally{fileBusy.value=false}}
async function downloadFile(role:string){if(fileBusy.value)return;fileBusy.value=true;detailError.value='';try{const value=await getFiles();if(!value.files[role])throw new Error('文件尚未上传');const a=document.createElement('a');a.href=value.files[role];a.target='_blank';a.rel='noopener';a.click()}catch(e){detailError.value=errorText(e)}finally{fileBusy.value=false}}
function downloadInstructions(){const o=order.value;if(!o)return;const text=[`订单：${o.number}`,`作品：${o.title}`,`尺寸：${o.spec.width_mm} × ${o.spec.height_mm} mm`,`纸张：${o.spec.paper}`,`装订：${o.spec.binding}`,`份数：${o.quantity}`,`内页：${o.page_count} 面，每份 ${o.sheets_per_copy} 张纸，${o.spec.duplex?'双面':'单面'}印刷`,'封面 PDF：第 1 面正封面，第 2 面封底。','内页按阅读顺序；无出血。请核对页序、裁切、装订方向与份数。'].join('\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`${o.number}-生产说明.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}

async function copyAddress(){if(!order.value)return;try{const a=order.value.address;await navigator.clipboard.writeText(`${a.name} ${a.phone}\n${a.region} ${a.detail}`);message.success('收货信息已复制')}catch{detailError.value='复制失败，请手动选择收货信息复制'}}
let timer:ReturnType<typeof setInterval>;
onMounted(()=>{void loadList();timer=setInterval(()=>{if(document.hidden||actionBusy.value||actionOpen.value)return;if(!listBusy.value)void loadList();if(!detailBusy.value)void loadDetail();if(previewURL.value&&links&&Date.parse(links.expires_at)<Date.now()+45000)void preview(previewRole.value,true)},30000)});
onUnmounted(()=>{clearInterval(timer);listSequence++;detailSequence++});
</script>
<style scoped>
.print-console{max-width:1560px;margin:auto;padding:24px}.heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}h1{font-size:26px;margin:0;font-weight:650}h2{font-size:23px;margin:0 0 8px}h3{font-size:16px;margin:0 0 8px}.muted{color:#7a8390;font-size:12px;margin-top:5px;overflow-wrap:anywhere}.queue-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:24px}.queue{border:1px solid #e5e9ee;background:#fff;border-radius:12px;padding:18px;text-align:left;cursor:pointer}.queue:hover{border-color:#91bfff}.queue.selected{border-color:#1677ff;background:#f0f7ff}.queue span,.queue small{display:block}.queue strong{display:block;font-size:30px;line-height:1.5}.queue small{color:#7a8390;font-size:12px}.orders-panel{background:#fff;border:1px solid #e5e9ee;border-radius:12px;padding:20px}.filters{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:20px}.pagination{display:flex;justify-content:flex-end;padding-top:20px}.book-title{font-weight:600}.order-number{font-size:11px;max-width:220px}.gap{margin-bottom:18px}.file-toolbar{margin-top:24px;margin-bottom:12px}.service-box,.address,.confirm-order{padding:16px;background:#f5f7fa;border-radius:10px;margin-bottom:18px}.service-box{background:#fff8ea;border:1px solid #ffe1a1}.shipment{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 0;border-bottom:1px solid #eee;margin-bottom:18px}.checklist{display:flex;flex-direction:column;gap:12px;padding:12px 0 24px}.preview{margin-top:20px;border:1px solid #e5e9ee;border-radius:10px;overflow:hidden}.preview-heading{padding:12px 16px;display:flex;justify-content:space-between;align-items:center;background:#f5f7fa}.preview iframe{border:0;width:100%;height:570px;background:#eef1f5}.preview p{padding:0 16px}.footer{min-height:44px;margin:0}@media(max-width:1100px){.queue-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:650px){.print-console{padding:12px}.queue-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.heading:not(.footer){align-items:flex-start;flex-direction:column}.orders-panel{padding:12px}.preview iframe{height:400px}}
</style>
