<template>
  <section class="campaigns">
    <header>
      <h1>实体书优惠活动</h1>
      <a-button v-if="canCreate" type="primary" @click="router.push(editor)">新建活动</a-button>
    </header>
    <a-alert v-if="error" type="error" show-icon :message="error">
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>
    <a-tabs v-model:active-key="tab">
      <a-tab-pane key="plans" tab="活动列表">
        <a-space wrap class="filters">
          <a-select v-model:value="source" :options="types" aria-label="活动类型" />
          <a-select v-model:value="state" :options="states" aria-label="活动状态" />
          <a-range-picker v-model:value="dates" aria-label="投放日期（北京时间）" />
        </a-space>
        <a-table :data-source="filteredPlans" :columns="planColumns" row-key="id" :loading="loading"
          :pagination="{pageSize:20,showSizeChanger:false}" :scroll="{x:950}"
          :locale="{emptyText:error?'活动列表加载失败':plans.length?'没有符合筛选的活动':'暂无活动'}">
          <template #bodyCell="{column,record:p}">
            <router-link v-if="column.key==='title'" :to="{path:editor,query:{id:p.id}}">{{p.title}}</router-link>
            <span v-else-if="column.key==='reward'">{{p.source==='pages'?'20 页半价 · 40 页免费档':p.annual_percent===50?'年费首购 · 半价券':'年费首购 · 标准装订抵扣券'}}</span>
            <span v-else-if="column.key==='schedule'">{{date(p.starts_at)}} 至 {{date(p.ends_at)}}</span>
            <template v-else-if="column.key==='quota'">
              {{p.quota-p.remaining}} / {{p.quota}}
              <a-tag v-if="p.state==='进行中' && p.remaining/p.quota<=0.2" color="orange">名额将满</a-tag>
            </template>
            <a-button v-else-if="column.key==='pending' && p.pending" type="link" @click="openReview(p.id)">{{p.pending}} 条</a-button>
            <span v-else-if="column.key==='pending'">0</span>
            <a-tag v-else-if="column.key==='state'" :color="p.state==='进行中'?'green':p.state==='已满额'?'orange':undefined">{{p.state}}</a-tag>
            <a-space v-else-if="column.key==='actions'">
              <router-link :to="{path:editor,query:{id:p.id}}">{{p.draft?'继续编辑':'查看'}}</router-link>
              <router-link :to="{path:'/print-campaigns/participants',query:{id:p.id}}">参与用户</router-link>
              <router-link v-if="canCreate" :to="{path:editor,query:{copy:p.id}}">复制</router-link>
              <a-popconfirm v-if="p.active && p.state!=='已结束'" title="暂停新报名？已报名用户仍可按原规则提交审核。" @confirm="submit({action:'pause',id:p.id})">
                <a-button type="link" size="small" :disabled="busy">暂停招募</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table>
      </a-tab-pane>
      <a-tab-pane key="review" :tab="pending===null?'达标审核':'达标审核（'+pending+'）'">
        <a-button v-if="reviewPlan" class="filters" @click="openReview()">查看全部活动的申请</a-button>
        <a-table :data-source="entries" :columns="reviewColumns" row-key="id" :loading="loading"
          :pagination="false" :locale="{emptyText:error?'审核队列加载失败':'暂无待审核申请'}">
          <template #bodyCell="{column,record:e}">
            <span v-if="column.key==='time'">{{date(e.created_at)}}</span>
            <span v-else-if="column.key==='pages'">申报 {{e.reported_pages}} 页 · 已核验 {{e.approved_pages}} 页</span>
            <a-button v-else-if="column.key==='actions'" type="link" @click="selected=e;reviewReason='';reviewPages=''">查看申请</a-button>
          </template>
        </a-table>
        <a-pagination v-if="pending && pending>20" v-model:current="page" :total="pending" :page-size="20" :show-size-changer="false" @change="load"/>
      </a-tab-pane>
    </a-tabs>
    <a-drawer :open="!!selected" title="达标审核" width="min(540px,100vw)" @close="selected=undefined">
      <template v-if="selected">
        <a-descriptions :column="1" bordered>
          <a-descriptions-item label="活动">{{selected.plan__title}}</a-descriptions-item>
          <a-descriptions-item label="账号">{{selected.owner_id}}</a-descriptions-item>
          <a-descriptions-item label="作品 ID">{{selected.book_id}}</a-descriptions-item>
          <a-descriptions-item label="申报 / 已核验">{{selected.reported_pages}} / {{selected.approved_pages}} 页</a-descriptions-item>
          <a-descriptions-item label="原券">{{couponStatus(selected)}}</a-descriptions-item>
        </a-descriptions>
        <a-alert class="review-note" type="info" message="页面展示用户申报记录，请核对作品依据后确认。" />
        <a-space v-if="canReview" wrap>
          <a-popconfirm v-for="tier in [halfThreshold,fullThreshold].filter(n=>n<=selected!.reported_pages && n>selected!.approved_pages)"
            :key="tier" :title="'确认已核验 '+tier+' 个有效内页？'" @confirm="approve(tier)">
            <a-button type="primary" :loading="busy">{{'通过 '+tier+' 页核验'}}</a-button>
          </a-popconfirm>
        </a-space>
        <a-form v-if="canReview" layout="vertical" class="review-note">
          <a-form-item label="退回或未通过原因"><a-textarea v-model:value="reviewReason" :maxlength="500" /></a-form-item>
          <a-form-item label="需完善的页面 ID（可选，用逗号分隔）"><a-textarea v-model:value="reviewPages" /></a-form-item>
          <a-space>
            <a-button :disabled="busy || !reviewReason.trim()" @click="reviewDecision('return')">退回补充</a-button>
            <a-button :disabled="busy || !reviewReason.trim()" @click="reviewDecision('reject')">记录未通过</a-button>
          </a-space>
        </a-form>
      </template>
    </a-drawer>
  </section>
</template>

<script setup lang="ts">
import {computed,onMounted,ref} from 'vue';
import {useRouter} from 'vue-router';
import {message} from 'ant-design-vue';
import type {Dayjs} from 'dayjs';
import http from '../api/http';
import {useAuthStore} from '../stores/auth';

const url='/api/admin/v1/print/campaigns/';
const editor='/print-campaigns/configure';
const router=useRouter(),auth=useAuthStore();
const canCreate=computed(()=>auth.user?.is_superuser || auth.hasPermission('print_orders.add_printcampaign'));
const canReview=computed(()=>auth.user?.is_superuser || auth.hasPermission('print_orders.change_printenrollment'));
type Plan={id:number,title:string,source:string,annual_percent:number,starts_at:string,ends_at:string,quota:number,active:boolean,draft:boolean,state:string,remaining:number,pending:number};
type Entry={id:number,attempt:number,plan__title:string,owner_id:number,book_id:string,reported_pages:number,approved_pages:number,created_at:string,coupon__percent:number|null,coupon__order_id:string|null,coupon__order__payment_state:string|null,coupon__order__file_state:string|null};
const plans=ref<Plan[]>([]),entries=ref<Entry[]>([]),selected=ref<Entry>();
const tab=ref('plans'),source=ref(''),state=ref(''),dates=ref<[Dayjs,Dayjs]>();
const reviewPlan=ref<number>();
const halfThreshold=ref(20),fullThreshold=ref(40);
const pending=ref<number|null>(null),page=ref(1),loading=ref(false),busy=ref(false),error=ref('');
const types=[{value:'',label:'全部类型'},{value:'pages',label:'制作达标'},{value:'annual',label:'年费首购'}];
const states=['','草稿','待开始','进行中','已满额','已暂停','已结束'].map(value=>({value,label:value||'全部状态'}));
const planColumns=[{title:'活动',key:'title'},{title:'奖励',key:'reward'},{title:'投放时间（北京时间）',key:'schedule'},
  {title:'已占名额',key:'quota'},{title:'待审',key:'pending'},{title:'状态',key:'state'},{title:'操作',key:'actions'}];
const reviewColumns=[{title:'活动',dataIndex:'plan__title'},{title:'账号',dataIndex:'owner_id'},{title:'申报时间',key:'time'},
  {title:'页数',key:'pages'},{title:'操作',key:'actions'}];
const dateFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
function date(value:string){return value?dateFormat.format(new Date(value)):'—'}
const filteredPlans=computed(()=>plans.value.filter(plan=>{
  if(source.value && plan.source!==source.value || state.value && plan.state!==state.value)return false;
  if(!dates.value?.[0] || !dates.value?.[1])return true;
  const start=Date.parse(dates.value[0].format('YYYY-MM-DD')+'T00:00:00+08:00');
  const end=Date.parse(dates.value[1].format('YYYY-MM-DD')+'T00:00:00+08:00')+86400000;
  return Date.parse(plan.starts_at)<end && Date.parse(plan.ends_at)>start;
}));
const reviewReason=ref(''),reviewPages=ref('');
let sequence=0;
async function load(){
  const key=++sequence;
  loading.value=true;error.value='';
  try{
    const data=await http.get(url,{params:{page:page.value,review_plan:reviewPlan.value}}) as unknown as {plans:Plan[],entries:Entry[],total_pending:number,half_threshold:number,full_threshold:number};
    if(key!==sequence)return;
    if(!Number.isInteger(data.total_pending) || !Array.isArray(data.entries) || !Array.isArray(data.plans))throw new Error('活动接口响应不完整');
    const last=Math.max(1,Math.ceil(data.total_pending/20));
    if(page.value>last){page.value=last;await load();return}
    halfThreshold.value=data.half_threshold ?? 20;fullThreshold.value=data.full_threshold ?? 40;plans.value=data.plans;entries.value=data.entries;pending.value=data.total_pending;
  }catch(e){if(key===sequence){error.value=String(e);pending.value=null;entries.value=[];plans.value=[]}}
  finally{if(key===sequence)loading.value=false}
}
async function submit(body:object){
  if(busy.value)return;
  busy.value=true;
  try{
    const result=await http.post(url,body) as unknown as {message:string};
    message.success(result.message);selected.value=undefined;await load();
  }catch(e){message.error(String(e))}
  finally{busy.value=false}
}
function openReview(plan?:number){reviewPlan.value=plan;page.value=1;tab.value='review';void load()}
function couponStatus(entry:Entry){
  if(!entry.coupon__percent)return '尚未发券';
  const name=entry.coupon__percent===100?'免费券':'半价券';
  if(!entry.coupon__order_id)return name+'已发放';
  const paid=['paid','refunded','refund_pending'].includes(entry.coupon__order__payment_state||'');
  const free=entry.coupon__order__payment_state==='not_required' && entry.coupon__order__file_state==='ready';
  return name+(paid||free?'已使用':'被订单占用')+' · '+entry.coupon__order_id;
}
function reviewDecision(action:string){
  if(!selected.value)return;
  return submit({action,id:selected.value.id,attempt:selected.value.attempt,reason:reviewReason.value.trim(),
    page_ids:reviewPages.value.split(/[,，\s]+/).filter(Boolean)});
}
function approve(tier:number){if(selected.value)return submit({action:'approve',id:selected.value.id,attempt:selected.value.attempt,tier})}
onMounted(load);
</script>

<style scoped>
header{display:flex;align-items:center;justify-content:space-between;gap:16px}
header h1{margin:0}
.filters{margin-bottom:16px}
.review-note{margin:16px 0}
</style>
