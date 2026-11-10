<template>
  <section>
    <router-link to="/print-campaigns">返回活动列表</router-link>
    <h1>{{title || '活动'}} · 参与用户</h1>
    <a-space wrap class="filters">
      <a-input-search v-model:value="query" placeholder="账号名称、账号 ID 或作品 ID" allow-clear @search="search"/>
      <a-select v-model:value="status" :options="statuses" @change="search" aria-label="参与状态"/>
    </a-space>
    <a-alert v-if="error" type="error" :message="error" show-icon>
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>
    <a-table :columns="columns" :data-source="rows" row-key="id" :loading="loading" :pagination="false" :scroll="{x:850}"
      :locale="{emptyText:error?'加载失败':query||status?'没有匹配的参与用户':'暂无参与用户'}">
      <template #bodyCell="{column,record}">
        <span v-if="column.key==='user'">{{record.username}} · {{record.owner_id}}</span>
        <span v-else-if="column.key==='created'">{{date(record.created_at)}}</span>
        <span v-else-if="column.key==='progress'">{{record.reported_pages}} / {{record.approved_pages}} 页</span>
        <a-tag v-else-if="column.key==='status'" :color="record.withdrawn_at?'default':'green'">{{participation(record)}}</a-tag>
        <span v-else-if="column.key==='coupon'">{{record.coupon_name ? record.coupon_name+' · ' : ''}}{{record.coupon_state}}</span>
        <a-button v-else-if="column.key==='details'" type="link" @click="selected=record">查看</a-button>
      </template>
    </a-table>
    <a-pagination v-if="total>20" v-model:current="page" :total="total" :page-size="20" :show-size-changer="false" @change="load"/>
    <a-drawer :open="!!selected" title="报名详情" width="min(520px,100vw)" @close="selected=undefined">
      <template v-if="selected">
        <a-descriptions :column="1" bordered>
          <a-descriptions-item label="账号">{{selected.username}} · {{selected.owner_id}}</a-descriptions-item>
          <a-descriptions-item label="作品 ID">{{selected.book_id || '—'}}</a-descriptions-item>
          <a-descriptions-item label="参与状态">{{participation(selected)}}</a-descriptions-item>
          <a-descriptions-item v-if="selected.review_reason" label="核验反馈">{{selected.review_reason}}</a-descriptions-item>
          <a-descriptions-item label="页数口径">{{selected.ai_pages_only?'本期 AI 制作内页':'原报名规则'}}</a-descriptions-item>
          <a-descriptions-item label="申报 / 核验">{{selected.reported_pages}} / {{selected.approved_pages}} 页</a-descriptions-item>
          <a-descriptions-item label="优惠券">
            <router-link v-if="selected.coupon_id" :to="{path:'/print-coupons',query:{q:selected.coupon_id}}">{{selected.coupon_name}} · {{selected.coupon_state}}</router-link>
            <span v-else>{{selected.coupon_state}}</span>
          </a-descriptions-item>
          <a-descriptions-item v-if="selected.order_id" label="关联订单">
            <router-link :to="{path:'/print-orders',query:{order:selected.order_id}}">{{selected.order_id}}</router-link>
          </a-descriptions-item>
        </a-descriptions>
        <details v-if="selected.page_evidence?.length"><summary>AI 制作内页依据（{{selected.page_evidence.length}} 条）</summary>
          <p v-for="(face,i) in selected.page_evidence" :key="i">{{face.page}} · {{face.face==='right'?'右页':'左页'}} · {{face.reason||'已计入'}}</p>
        </details>
        <h3 class="history">参与记录</h3>
        <a-timeline>
          <a-timeline-item v-for="(event,index) in selected.history" :key="index">
            {{date(event.at)}} · {{eventLabel(event)}}<br/>
            <span v-if="event.book_id">作品 {{event.book_id}}</span>
          </a-timeline-item>
        </a-timeline>
      </template>
    </a-drawer>
  </section>
</template>

<script setup lang="ts">
import {ref,watch} from 'vue';
import {useRoute} from 'vue-router';
import http from '../api/http';

type Participant={id:number,owner_id:number,username:string,book_id:string|null,created_at:string,withdrawn_at:string|null,
  reported_pages:number,approved_pages:number,review_decision:string,review_reason:string,half_threshold:number,full_threshold:number,reward_completed:boolean,coupon_id:string|null,coupon_name:string|null,coupon_state:string,order_id:string|null,
  ai_pages_only:boolean,page_evidence?:{page:string,face:string,reason:string}[],history:{event:string,at:string,book_id:string|null,reported_pages?:number,approved_pages?:number}[]};
const route=useRoute();
const title=ref(''), query=ref(''), status=ref(''), error=ref(''), page=ref(1), total=ref(0), loading=ref(false);
const rows=ref<Participant[]>([]), selected=ref<Participant>();
const statuses=[{value:'',label:'全部状态'},{value:'joined',label:'参与中'},{value:'withdrawn',label:'已退出'}];
const columns=[{title:'用户',key:'user'},{title:'作品 ID',dataIndex:'book_id'},{title:'首次报名',key:'created'},
  {title:'申报 / 核验',key:'progress'},{title:'参与状态',key:'status'},{title:'优惠券',key:'coupon'},{title:'操作',key:'details'}];
const formatter=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',dateStyle:'medium',timeStyle:'short'});
const date=(value:string)=>formatter.format(new Date(value));
function participation(row:Participant){
  if(row.withdrawn_at)return '已退出';
  if(row.reward_completed)return '奖励已完成';
  if(row.review_decision==='returned')return '待补充';
  if(row.review_decision==='rejected')return '未通过';
  if(row.reported_pages>=row.full_threshold && row.approved_pages<row.full_threshold || row.reported_pages>=row.half_threshold && row.approved_pages<row.half_threshold)return '待核验';
  return '参与中';
}
function eventLabel(event:Participant['history'][number]){
  if(event.event==='withdrawn')return '退出活动';
  if(event.event==='progress')return '申报 '+event.reported_pages+' 页';
  if(event.event==='approved')return '核验通过 '+event.approved_pages+' 页';
  return '报名';
}
let sequence=0;
async function load(){
  const key=++sequence;
  loading.value=true;
  error.value='';
  try {
    const data=await http.get('/api/admin/v1/print/campaigns/',{params:{
      participants:route.query.id,q:query.value,status:status.value,page:page.value,
    }}) as unknown as {title:string,total:number,participants:Participant[]};
    if(key!==sequence)return;
    title.value=data.title;total.value=data.total;rows.value=data.participants;
  } catch(e){
    if(key===sequence){error.value=String(e);rows.value=[];total.value=0}
  } finally {
    if(key===sequence)loading.value=false;
  }
}
function search(){page.value=1;void load()}
watch(()=>route.query.id,()=>{selected.value=undefined;search()},{immediate:true});
</script>

<style scoped>
.filters{margin-bottom:16px}
.history{margin-top:24px}
.ant-pagination{margin-top:16px}
</style>
