<template>
 <a-drawer :open="open" title="印制规格" width="min(900px, 100vw)" :mask-closable="!saving" @close="close">
  <a-alert v-if="error" type="error" show-icon :message="error" class="gap" />
  <p class="muted">配置 A5 / B5 的材料、配送和打样记录，完成后再开放接单。</p>
  <div class="spec-list">
   <button v-for="p in products" :key="p.id" class="spec-card" :class="{selected:product?.id===p.id}" @click="choose(p)">
    <strong>{{p.title}}</strong><a-tag :color="p.active?'green':'default'">{{p.active?'已开放':'未开放'}}</a-tag>
    <span>{{p.width_mm}} × {{p.height_mm}} mm · {{p.free_printing?'印制免费':'收费印制'}}</span>
    <small>{{p.proof_approved?'已完成打样':'待实物打样'}} · 运费 ¥{{money(p.shipping_fen)}}</small>
   </button>
   <a-button @click="choose()">＋ 新增规格</a-button>
  </div>
  <a-spin :spinning="loading">
   <a-form v-if="product" layout="vertical" :disabled="saving">
    <a-divider orientation="left">1. 成品与材料</a-divider>
    <a-form-item label="规格名称" required><a-input v-model:value="product.title" :maxlength="120" /></a-form-item>
    <div class="grid"><a-form-item label="宽度（mm）" required><a-input-number v-model:value="product.width_mm" :min="1" :max="500" :precision="0" /></a-form-item><a-form-item label="高度（mm）" required><a-input-number v-model:value="product.height_mm" :min="1" :max="500" :precision="0" /></a-form-item></div>
    <div class="grid"><a-form-item label="纸张" required><a-input v-model:value="product.paper" placeholder="纸张名称、克重等" :maxlength="120" /></a-form-item><a-form-item label="装订工艺" required><a-input v-model:value="product.binding" :maxlength="120" /></a-form-item></div>
    <a-form-item label="规格说明"><a-textarea v-model:value="product.description" :rows="2" /></a-form-item>
    <a-alert type="info" message="无出血；有外壳时单独交付外壳；全部内容页按阅读顺序作为内页，不抽取末页。" show-icon />
    <a-divider orientation="left">2. 印刷数量</a-divider>
    <a-form-item label="内页双面印刷"><a-switch v-model:checked="product.duplex" /><span class="muted"> {{product.duplex?'每张内页纸印两面':'每张内页纸印一面'}}；外壳（如有）不计入内页面数。</span></a-form-item>
    <div class="grid three"><a-form-item label="最少内页面数"><a-input-number v-model:value="product.min_pages" :min="1" :max="500" :precision="0" /></a-form-item><a-form-item label="最多内页面数"><a-input-number v-model:value="product.max_pages" :min="1" :max="500" :precision="0" /></a-form-item><a-form-item label="每单最多份数"><a-input-number v-model:value="product.max_quantity" :min="1" :max="100" :precision="0" /></a-form-item></div>
    <a-divider orientation="left">3. 费用与配送</a-divider>
    <a-form-item label="印制免费"><a-switch v-model:checked="product.free_printing" /></a-form-item>
    <div v-if="!product.free_printing" class="grid"><a-form-item label="每份基础费（元）"><a-input-number :value="product.base_fen/100" :min="0" :precision="2" @change="(v: number|string|null)=>product && (product.base_fen=Math.round(Number(v)*100))" /></a-form-item><a-form-item label="每内页面费用（元）"><a-input-number :value="product.page_fen/100" :min="0" :precision="2" @change="(v: number|string|null)=>product && (product.page_fen=Math.round(Number(v)*100))" /></a-form-item></div>
    <a-form-item label="整单运费（元）"><a-input-number :value="product.shipping_fen/100" :min="0" :precision="2" @change="(v: number|string|null)=>product && (product.shipping_fen=Math.round(Number(v)*100))" /></a-form-item>
    <div class="quote-box">费用示例：<a-input-number v-model:value="examplePages" :min="product.min_pages" :max="product.max_pages" :precision="0" size="small" /> 面 × <a-input-number v-model:value="exampleQuantity" :min="1" :max="product.max_quantity" :precision="0" size="small" /> 份
     <p>印制 ¥{{money(exampleProduction)}} ＋ 运费 ¥{{money(product.shipping_fen)}} ＝ <strong>用户支付 ¥{{money(exampleProduction+product.shipping_fen)}}</strong></p>
    </div>
    <a-form-item label="支持配送地区" required extra="使用统一地区名称；输入后回车添加，重复名称自动合并。"><a-select v-model:value="product.regions" mode="tags" :token-separators="[',','，',';','；']" placeholder="如：上海市、江苏省" /></a-form-item>
    <a-form-item label="制作周期说明" required><a-input v-model:value="product.lead_time" placeholder="填写已确认的制作与发货时间" :maxlength="200" /></a-form-item>
    <a-form-item label="购买、退改和售后说明" required><a-textarea v-model:value="product.terms" :rows="4" /></a-form-item>
    <a-divider orientation="left">4. 实物打样与开放</a-divider>
    <a-form-item label="打样记录"><a-textarea v-model:value="product.proof_note" :rows="3" placeholder="填写打样材料、装订工艺、尺寸与印刷检查结果" /></a-form-item>
    <a-checkbox v-model:checked="product.proof_approved">该规格已实物打样通过</a-checkbox>
    <p class="muted" v-if="product.proof_at">{{product.proof_by}} · {{date(product.proof_at)}}</p>
    <a-checkbox v-if="materialChanged" v-model:checked="reproof">材料或工艺已改变，我已按当前参数重新实物打样</a-checkbox>
    <div class="readiness"><strong>开放检查</strong><p v-for="item in readiness" :key="item.name"><span :class="item.ok?'ok':'missing'">{{item.ok?'✓':'○'}}</span> {{item.name}}</p></div>
    <a-form-item label="向用户开放"><a-switch v-model:checked="product.active" :disabled="!ready && !product.active" /><span class="muted"> {{ready?'已满足开放条件，可开放接单':'完成以上检查后可开放'}}</span></a-form-item>
   </a-form>
  </a-spin>
  <template #footer><a-alert v-if="error" type="error" show-icon :message="error" class="gap" /><div class="footer"><span class="muted">{{dirty?'有未保存的修改':'修改只影响之后的新订单'}}</span><a-space><a-button :disabled="saving" @click="close">关闭</a-button><a-button type="primary" :loading="saving" :disabled="!product" @click="save">保存规格</a-button></a-space></div></template>
 </a-drawer>
</template>
<script setup lang="ts">
import {computed,ref,watch,onMounted,onUnmounted,toRaw} from 'vue';
import {Modal,message} from 'ant-design-vue';
import http from '../../api/http';
import {type Product,money,date,errorText} from './types';
const props=defineProps<{open:boolean}>(),emit=defineEmits<{close:[]}>();
const products=ref<Product[]>([]),product=ref<Product>(),original=ref(''),error=ref(''),loading=ref(false),saving=ref(false),reproof=ref(false);
const examplePages=ref(20),exampleQuantity=ref(1);
const dirty=computed(()=>!!product.value && JSON.stringify(product.value)!==original.value);
const materialChanged=computed(()=>{if(!product.value||!original.value)return false;const before=JSON.parse(original.value);return before.proof_approved && ['width_mm','height_mm','paper','binding','duplex'].some(k=>before[k]!== (product.value as unknown as Record<string,unknown>)[k])});
const readiness=computed(()=>{const p=product.value;if(!p)return [];return [{name:'纸张与装订工艺',ok:!!p.paper.trim()&&!!p.binding.trim()},{name:'打样通过并填写记录',ok:p.proof_approved&&!!p.proof_note.trim()&&(!materialChanged.value||reproof.value)},{name:'免费或有效价格',ok:p.free_printing||p.base_fen+p.page_fen*p.min_pages>0},{name:'配送地区与制作周期',ok:p.regions.some(x=>x.trim())&&!!p.lead_time.trim()},{name:'购买、退改和售后说明',ok:!!p.terms.trim()}]});
const ready=computed(()=>readiness.value.length>0&&readiness.value.every(x=>x.ok));
const exampleProduction=computed(()=>{const p=product.value;return !p||p.free_printing?0:(p.base_fen+p.page_fen*(examplePages.value||p.min_pages))*(exampleQuantity.value||1)});
function discard(next:()=>void){if(saving.value)return;if(dirty.value)Modal.confirm({title:'放弃未保存的规格修改？',content:'当前修改尚未保存。',okText:'放弃修改',cancelText:'继续编辑',onOk:next});else next()}
function setProduct(p?:Product){product.value=p?structuredClone(toRaw(p)):{title:'',active:false,proof_approved:false,proof_note:'',revision:1,width_mm:148,height_mm:210,paper:'',binding:'',description:'',cover_mode:'optional_shell',duplex:true,min_pages:2,max_pages:200,max_quantity:10,free_printing:true,base_fen:0,page_fen:0,shipping_fen:0,regions:[],lead_time:'',terms:''};original.value=JSON.stringify(product.value);error.value='';reproof.value=false}
function choose(p?:Product){discard(()=>setProduct(p))}
function close(){discard(()=>{product.value=undefined;emit('close')})}
watch(()=>props.open,async open=>{if(!open)return;loading.value=true;error.value='';try{products.value=await http.get('/api/admin/v1/print/products/') as unknown as Product[];setProduct(products.value[0])}catch(e){error.value=errorText(e)}finally{loading.value=false}});
async function save(){if(!product.value||saving.value)return;const p=product.value;error.value='';
 if(!p.title.trim()){error.value='请填写规格名称';return}
 const numbers=[p.width_mm,p.height_mm,p.min_pages,p.max_pages,p.max_quantity];
 if(numbers.some(v=>!Number.isInteger(v)||v<1)||p.width_mm>500||p.height_mm>500||p.max_pages>500||p.max_quantity>100||p.min_pages>p.max_pages){error.value='请检查尺寸、页数上下限和份数，均须为有效整数';return}
 if([p.base_fen,p.page_fen,p.shipping_fen].some(v=>!Number.isInteger(v)||v<0)){error.value='费用不能为负数或空值';return}
 if(p.active&&!ready.value){error.value='请完成开放检查，或关闭“向用户开放”后保存草稿';return}
 if(p.proof_approved&&!p.proof_note.trim()){error.value='请补充实物打样记录';return}
 saving.value=true;try{const saved=await http.post('/api/admin/v1/print/products/',{...p,regions:[...new Set(p.regions.map(x=>x.trim()).filter(Boolean))],reproof_confirmed:reproof.value}) as unknown as Product;setProduct(saved);products.value=[...products.value.filter(x=>x.id!==saved.id),saved];message.success('规格已保存')}catch(e){error.value=errorText(e)}finally{saving.value=false}}
function beforeUnload(e:BeforeUnloadEvent){if(props.open&&dirty.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>window.addEventListener('beforeunload',beforeUnload));onUnmounted(()=>window.removeEventListener('beforeunload',beforeUnload));
</script>
<style scoped>
.gap{margin-bottom:16px}.muted{color:#77818b;font-size:13px}.spec-list{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.spec-card{border:1px solid #dce2e7;border-radius:12px;background:#fff;padding:16px;text-align:left;cursor:pointer;min-width:210px}.spec-card strong{margin-right:12px}.spec-card span,.spec-card small{display:block;margin-top:8px}.spec-card.selected{border-color:#1677ff;background:#f0f7ff}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.three{grid-template-columns:repeat(3,minmax(0,1fr))}.quote-box,.readiness{padding:16px;background:#f5f7fa;border-radius:10px;margin-bottom:20px}.quote-box .ant-input-number{width:75px}.readiness p{margin:8px 0}.ok{color:#389e0d}.missing{color:#ad6800}.footer{display:flex;justify-content:space-between;gap:12px;align-items:center}@media(max-width:600px){.grid,.three{grid-template-columns:1fr}.spec-card{width:100%}}
</style>
