<template>
  <section>
    <header><h1>印制优惠券</h1><a-button v-if="canGrant" type="primary" @click="open=true">定向发券</a-button></header>
    <a-space wrap><a-input-search v-model:value="q" placeholder="账号、券号、订单号或工单" allow-clear @search="search"/>
    <a-select v-model:value="source" :options="sources" @change="search"/>
    <a-select v-model:value="state" :options="states" @change="search"/></a-space>
    <a-alert v-if="err" type="error" :message="err"><template #action><a-button @click="load">重试</a-button></template></a-alert>
    <a-table :loading="loading" :data-source="rows" :columns="columns" row-key="id" :pagination="false" :scroll="{x:1100}" :locale="{emptyText:err?'加载失败':q||state||source?'没有匹配的优惠券':'暂无发券记录'}"/>
    <a-pagination v-model:current="page" :total="total" :page-size="20" :show-size-changer="false" @change="load"/>
    <a-drawer v-model:open="open" title="定向发券" width="min(520px,100vw)">
    <a-form :disabled="busy" layout="vertical" @finish="grant">
      <a-form-item label="用户账号 ID"><a-input-number v-model:value="form.owner" :min="1" /></a-form-item>
      <a-form-item label="印制商品 ID"><a-select v-model:value="form.product" placeholder="选择已打样的在售规格" :options="products.map(p=>({value:p.id,label:p.title}))"/></a-form-item>
      <a-form-item label="活动工单号（同账号同工单只发一次）"><a-input v-model:value="form.ticket" /></a-form-item>
      <a-form-item label="优惠"><a-select v-model:value="form.percent" :options="[{value:50,label:'标准装订半价'},{value:100,label:'标准装订全额抵扣'}]" /></a-form-item>
      <a-form-item label="每券包含内页数"><a-input-number v-model:value="form.included_pages" :min="1" /></a-form-item>
      <a-form-item label="最高抵扣（元）"><a-input-number v-model:value="cap" :min="0.01" :precision="2" /></a-form-item>
      <a-form-item label="到期时间"><input v-model="expiry" type="datetime-local" required /></a-form-item>
      <a-alert v-if="preview" type="info" :message="preview"/>
      <a-alert v-if="receipt" type="success" :message="receipt"/>
      <a-button type="primary" html-type="submit" :loading="busy">{{preview?'确认向该用户发放一张':'核对用户并试算'}}</a-button>
    </a-form>
    </a-drawer>
  </section>
</template>
<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import http from '../api/http';
import {useRoute} from 'vue-router';
import {useAuthStore} from '../stores/auth';
const auth=useAuthStore();
const canGrant=auth.user?.is_superuser || auth.hasPermission('print_orders.add_printcoupon');
const q=ref(''),state=ref(''),source=ref(''),page=ref(1),total=ref(0),loading=ref(false),err=ref(''),open=ref(false),preview=ref(''),receipt=ref('');
const confirmation=ref('');
const products=ref<{id:string,title:string}[]>([]);
const sources=[['','全部来源'],['manual','定向'],['annual','年费'],['campaign','制作达标']].map(([value,label])=>({value,label}));
const states=['','可用','已使用','订单占用','已到期'].map(value=>({value,label:value||'全部状态'}));
function search(){page.value=1;void load()}
const url='/api/admin/v1/print/coupons/';
const form=reactive({owner:undefined as number|undefined, product:'', ticket:'', percent:50, included_pages:20});
const cap=ref<number>(), expiry=ref(''), busy=ref(false), rows=ref<object[]>([]);
const columns=[['账号','owner_id'],['券名','name'],['状态','state'],['来源','source'],['规格','product'],['工单','ticket'],['到期','expires_at'],['关联订单','order_id'],['券号','id']].map(([title,dataIndex])=>({title,dataIndex}));
watch([form,cap,expiry],()=>{preview.value='';receipt.value=''}, {deep:true,flush:'sync'});
let seq=0;
async function load(){
  const key=++seq;loading.value=true;err.value='';
  try {
    const data=await http.get(url,{params:{q:q.value,state:state.value,source:source.value,page:page.value}}) as unknown as {results:object[],total:number,products:typeof products.value};
    if(key===seq){rows.value=data.results;total.value=data.total;products.value=data.products}
  }catch(e){if(key===seq){err.value=String(e);rows.value=[]}}finally{if(key===seq)loading.value=false}
}
async function grant() {
  if (busy.value) return;
  if (!form.owner || !form.product.trim() || !form.ticket.trim() || !cap.value || !expiry.value) {
    message.error('请填写完整的发放条件'); return;
  }
  busy.value=true;
  try {
    const body={...form,cap_fen:Math.round(cap.value*100),expires_at:new Date(expiry.value).toISOString()};
    if(!preview.value){
      const data=await http.post(url,{...body,preview:true}) as unknown as {account:string,product:string,pages:number,discount:number,total:number,shipping:number,confirmation:string};
      confirmation.value=data.confirmation;
      preview.value=String(data.account)+'（账号 '+form.owner+'） · '+data.product+' '+data.pages+' 页一册，运费 ¥'+(data.shipping/100).toFixed(2)+'，本券减 ¥'+(data.discount/100).toFixed(2)+'，实付 ¥'+(data.total/100).toFixed(2);
      return;
    }
    const r=await http.post(url,{...body,confirmation:confirmation.value}) as unknown as {created:boolean,id:string};
    receipt.value=(r.created?'新券已发放':'该工单此前已发放')+' · '+r.id;preview.value='';await load();
  } catch(e) { preview.value=''; message.error(String(e)); } finally { busy.value=false; }
}
const route=useRoute();
watch(()=>route.query.q,value=>{q.value=typeof value==='string'?value:'';search()},{immediate:true});
</script>

<style scoped>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px} .ant-table-wrapper{margin:18px 0}</style>
