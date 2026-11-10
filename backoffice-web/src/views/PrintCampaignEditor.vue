<template>
  <section>
    <router-link to="/print-campaigns">返回活动列表</router-link>
    <router-link v-if="editing" class="participants-link" :to="{path:'/print-campaigns/participants',query:{id:editing}}">参与用户</router-link>
    <h1>{{ readonly ? '活动详情' : editing ? '编辑活动草稿' : '新建活动' }}</h1>
    <a-alert v-if="error" type="error" show-icon :message="error">
      <template v-if="!ready" #action><a-button size="small" @click="retry++">重试</a-button></template>
    </a-alert>
    <a-spin :spinning="loading">
      <div v-if="ready" class="editor">
        <a-form ref="formRef" layout="vertical" :model="validationModel" :rules="rules" :disabled="busy || readonly">
          <a-card title="活动与投放">
            <a-form-item label="活动标题" name="title"><a-input v-model:value="form.title" placeholder="例如：旅行手帐制作达标礼" :maxlength="100" show-count /></a-form-item>
            <a-form-item label="参与方式"><a-select v-model:value="form.source" :options="types" /></a-form-item>
            <a-form-item v-if="form.source==='annual'" label="年费商品 ID" name="annual_product_id"><a-input v-model:value="form.annual_product_id" /></a-form-item>
            <a-form-item label="报名开始 / 截止（北京时间）" name="schedule"><a-space wrap>
              <input v-model="start" type="datetime-local" :disabled="busy || readonly" aria-label="开始时间"/>
              <input v-model="end" type="datetime-local" :disabled="busy || readonly" aria-label="截止时间"/>
            </a-space></a-form-item>
          </a-card>
          <a-card title="奖励与名额">
            <p v-if="form.source==='pages'">20 个有效内页享半价，40 个有效内页可升级免费档。申报和报名使用同一截止时间。</p>
            <a-form-item v-else label="首购赠券"><a-select v-model:value="form.annual_percent" :options="[{value:50,label:'半价券'},{value:100,label:'标准装订抵扣券'}]" /></a-form-item>
            <a-form-item label="适用印制规格" name="product"><a-select v-model:value="form.product" :options="[{value:unrestricted,label:'不限印制规格'}, ...products.map(p=>({value:p.id,label:p.title}))]" placeholder="请选择适用规格" /></a-form-item>
            <a-space wrap align="start">
              <a-form-item label="活动名额" name="quota"><a-input-number v-model:value="form.quota" :min="1" :precision="0"/></a-form-item>
              <a-form-item label="优惠覆盖的印制页数" name="included_pages"><a-input-number v-model:value="form.included_pages" :min="1" :precision="0"/></a-form-item>
              <a-form-item label="每券最高抵扣（元）" name="cap"><a-input-number v-model:value="cap" :min="0.01" :precision="2"/></a-form-item>
              <a-form-item label="到账后有效天数" name="valid_days"><a-input-number v-model:value="form.valid_days" :min="1" :precision="0"/></a-form-item>
            </a-space>
            <p>券有效期至少覆盖活动截止日，运费另计。</p>
          </a-card>
        </a-form>
        <aside>
          <a-card title="投放预览">
            <h3>{{ form.title || '活动标题' }}</h3>
            <p>{{ form.source==='pages' ? '完成画布后在作品预览展示。20 页半价，40 页免费档。' : '在指定年费套餐旁展示首次付费赠礼。' }}</p>
            <p v-if="form.product===unrestricted">适用于所有已开放印制规格，按所选规格计算抵扣。</p>
            <p>每券最高减 {{ money(Math.round(cap*100)) }} · 运费另计</p>
            <p v-if="form.quota">最高承诺 {{ form.quota }} × {{ money(Math.round(cap*100)) }} = {{ money(Math.round(cap*100)*form.quota) }}</p>
          </a-card>
          <a-card title="样单试算">
            <a-button :loading="busy" @click="preview(false)">计算实付</a-button>
            <template v-if="sample">
              <div v-for="item in sample.quotes || [sample]" :key="item.product" class="sample-quote">
                <p>{{ item.product }} · {{ item.pages }} 页一册 · {{ item.region }}</p>
                <p>印制 {{ money(item.production) }}，运费 {{ money(item.shipping) }}</p>
                <p v-for="tier in item.samples" :key="tier.percent">{{ tier.percent }}% 抵扣档 · 减 {{ money(tier.discount) }} · 实付 <strong>{{ money(tier.payable) }}</strong></p>
              </div>
            </template>
          </a-card>
        </aside>
      </div>
      <footer v-if="ready && !readonly">
        <a-button :disabled="busy" @click="saveAndReturn">保存草稿</a-button>
        <a-button type="primary" :loading="busy" @click="preview(true)">预览并发布</a-button>
      </footer>
    </a-spin>
    <a-modal v-model:open="confirm" title="确认投放" ok-text="确认发布" :confirm-loading="busy" @ok="publish">
      <h3>{{ form.title }}</h3>
      <p>{{ form.source==='pages' ? '制作达标用户 · 20 页半价，40 页免费档' : '指定年费首购用户 · '+form.annual_product_id }}</p>
      <p>{{ start.replace('T',' ') }} 至 {{ end.replace('T',' ') }}（北京时间）</p>
      <p v-if="sample">最高承诺 {{ money(sample.maximum) }} · {{ (sample.quotes || [sample]).map(q=>q.product+' 样单实付 '+q.samples.map(s=>money(s.payable)).join(' / ')).join('；') }}</p>
    </a-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance, FormProps } from 'ant-design-vue';
import http from '../api/http';

const url='/api/admin/v1/print/campaigns/';
const route=useRoute(), router=useRouter();
const types=[{value:'pages',label:'制作达标赠券'},{value:'annual',label:'年费开通赠券'}];
const unrestricted='all';
const defaults={title:'',source:'pages',product:'',annual_product_id:'',annual_percent:100,included_pages:20,quota:null as number|null,valid_days:30};
const form=reactive({...defaults});
type Plan=Omit<typeof defaults,'product'> & {product:string|null,id:number,draft:boolean,version:string,starts_at:string,ends_at:string,cap_fen:number};
type SampleQuote={product:string,pages:number,region:string,production:number,shipping:number,samples:{percent:number,discount:number,payable:number}[]};
type Sample=SampleQuote & {maximum:number,quotes?:SampleQuote[]};
const products=ref<{id:string,title:string}[]>([]);
const start=ref(''),end=ref(''),cap=ref(0),error=ref(''),version=ref('');
const editing=ref<number>(),readonly=ref(false),busy=ref(false),loading=ref(false),ready=ref(false),confirm=ref(false);
const sample=ref<Sample>(),retry=ref(0);
const money=(fen:number)=>'¥'+(fen/100).toFixed(2);
function beijingInput(value:string){return new Date(Date.parse(value)+8*3600000).toISOString().slice(0,19)}
const formRef=ref<FormInstance>();
const validationModel=computed(()=>({...form,cap:cap.value,schedule:[start.value,end.value]}));
const rules: NonNullable<FormProps['rules']> = {
  title:[{required:true,whitespace:true,message:'请输入活动标题'},{max:100,message:'活动标题最多 100 个字'}],
  product:[{required:true,message:'请选择适用印制规格'}],
  annual_product_id:[{validator:async()=>{
    if(form.source==='annual' && !form.annual_product_id.trim())throw new Error('请输入年费商品 ID');
  }}],
  schedule:[{validator:async()=>{
    if(!start.value || !end.value)throw new Error('请选择报名开始和截止时间');
    const begins=Date.parse(start.value+'+08:00'),ends=Date.parse(end.value+'+08:00');
    if(!Number.isFinite(begins)||!Number.isFinite(ends))throw new Error('请填写有效的报名时间');
    if(begins>=ends)throw new Error('报名截止时间须晚于开始时间');
    if(!readonly.value && ends<=Date.now())throw new Error('报名截止时间须晚于当前时间');
  }}],
  quota:[{type:'integer',required:true,min:1,message:'请输入大于零的整数名额'}],
  included_pages:[{type:'integer',required:true,min:1,message:'请输入大于零的整数页数'}],
  valid_days:[{type:'integer',required:true,min:1,message:'请输入大于零的整数天数'}],
  cap:[{type:'number',required:true,min:0.01,message:'抵扣上限至少为 0.01 元'}],
};
function errorMessage(value:unknown){
  return value instanceof Error ? value.message : '请求失败，请重试';
}
function payload(){
  if (!start.value || !end.value) throw new Error('请选择报名开始和截止时间');
  if (!form.product) throw new Error('请选择适用印制规格');
  return {...form,title:form.title.trim(),annual_product_id:form.annual_product_id.trim(),product:form.product===unrestricted?null:form.product,cap_fen:Math.round(cap.value*100),starts_at:new Date(start.value+'+08:00').toISOString(),
    ends_at:new Date(end.value+'+08:00').toISOString(),active:false};
}
watch([form,start,end,cap],()=>{sample.value=undefined},{deep:true});
watch(()=>[route.query.id,route.query.copy,retry.value] as const,async ([id,copy],_,onCleanup)=>{
  let current=true;
  onCleanup(()=>{current=false});
  ready.value=false;loading.value=true;error.value='';readonly.value=false;editing.value=undefined;
  Object.assign(form,defaults);start.value='';end.value='';cap.value=0;
  try {
    const [catalog,plan]=await Promise.all([
      http.get(url) as unknown as Promise<{products:typeof products.value}>,
      id||copy ? http.get(url,{params:{id:id||copy}}) as unknown as Promise<Plan> : undefined,
    ]);
    if(!current)return;
    products.value=catalog.products;
    if(plan){
      for(const key of Object.keys(defaults) as (keyof typeof defaults)[]) Object.assign(form,{[key]:plan[key]});
      form.product=plan.product ?? unrestricted;
      cap.value=plan.cap_fen/100;
      if(copy){form.title+='（新一期）';form.quota=null;}
      else{
        editing.value=plan.id;version.value=plan.version;readonly.value=!plan.draft;
        start.value=beijingInput(plan.starts_at);end.value=beijingInput(plan.ends_at);
        if(plan.product && !products.value.some(p=>p.id===plan.product))products.value.push({id:plan.product,title:'原规格（当前不可投放）'});
      }
    }
    ready.value=true;
  } catch(e){if(current)error.value=errorMessage(e)}
  finally{if(current)loading.value=false}
},{immediate:true});
async function save(){
  const data=await http.post(url,{...payload(),action:editing.value?'update':'create',id:editing.value,version:version.value}) as unknown as {id:number,version:string};
  editing.value=data.id;version.value=data.version;
}
async function run(action:()=>Promise<void>){
  if(busy.value)return;
  busy.value=true;error.value='';
  try{
    await formRef.value?.validate();
    await action();
  }catch(e){
    const fields=(e as {errorFields?:{name:(string|number)[]}[]})?.errorFields;
    if(fields?.length){
      error.value='请检查标红的必填项';
      formRef.value?.scrollToField(fields[0]!.name,{block:'center'});
    }else{
      error.value=errorMessage(e);
    }
  }finally{busy.value=false}
}
function saveAndReturn(){return run(async()=>{await save();message.success('草稿已保存');await router.push('/print-campaigns')})}
function preview(publishing:boolean){
  return run(async()=>{
    sample.value=await http.post(url,{...payload(),action:'preview'}) as unknown as Sample;
    confirm.value=publishing;
  });
}
function publish(){
  return run(async()=>{
    confirm.value=false;
    await save();
    await http.post(url,{action:'publish',id:editing.value,version:version.value});
    message.success('活动已发布');await router.push('/print-campaigns');
  });
}
</script>

<style scoped>
.editor{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);gap:20px;margin-top:18px}
.participants-link{margin-left:16px}
.ant-card{margin-bottom:16px}
footer{position:sticky;bottom:0;display:flex;justify-content:flex-end;gap:12px;padding:16px;background:var(--ant-color-bg-container,#fff)}
@media(max-width:950px){.editor{grid-template-columns:1fr}}
</style>
