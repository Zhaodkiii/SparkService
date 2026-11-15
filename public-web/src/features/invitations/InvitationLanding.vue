<template>
  <main class="invite-page"><article>
    <p class="brand">寻寻仔 · 旅行手帐</p><h1>{{campaign?.title || '与好友一起收藏旅途'}}</h1>
    <p>登记后下载 App，使用相同手机号登录或验证绑定，或绑定相同邮箱，即可确认邀请。</p>
    <p v-if="loading" role="status">正在读取邀请…</p>
    <p v-if="error" role="alert" class="error">{{error}}</p>
    <template v-if="campaign">
      <div class="rules">{{campaign.rules}}</div>
      <p>活动截至 {{new Date(campaign.ends_at).toLocaleString()}}</p>
      <form v-if="campaign.available && !registered" @submit.prevent="submit">
        <label>登记方式<select v-model="kind"><option value="phone">手机号</option><option value="email">邮箱</option></select></label>
        <label>{{kind==='phone'?'手机号（支持 +86 等国家区号）':'邮箱地址'}}<input v-model="contact" :type="kind==='phone'?'tel':'email'" :autocomplete="kind==='phone'?'tel':'email'" required maxlength="254" :disabled="busy" /></label>
        <p class="small">联系方式仅用于匹配邀请，不会显示给邀请人。登记不代表邀请成功，需在 App 内验证登录或绑定。请确认当前链接来自你希望接受的邀请人。</p>
        <label class="agree"><input v-model="consent" type="checkbox" required/>我已阅读活动规则及<a href="https://www.dreamwhale.top/legal/privacy/" target="_blank" rel="noopener">隐私政策</a></label>
        <button :disabled="busy || !consent">{{busy?'正在登记…':'确认登记并前往 App Store'}}</button>
      </form>
      <p v-else-if="!campaign.available">活动已结束或暂停，暂不可登记。</p>
      <section v-if="registered" role="status"><h2>登记成功</h2><p>请在 App 中使用刚才填写的联系方式登录或绑定。若没有自动打开，请点击下方按钮。</p><a class="download" :href="campaign.download_url">打开 App Store 下载</a></section>
    </template>
    <p v-if="!token">请通过好友分享的二维码进入邀请活动。</p>
  </article></main>
</template>
<script setup lang="ts">
import {ref,onMounted} from 'vue'
import {useRoute} from 'vue-router'
type Campaign={title:string;rules:string;ends_at:string;available:boolean;download_url:string}
const token=String(useRoute().params.token||'')
const campaign=ref<Campaign>(),loading=ref(false),busy=ref(false),error=ref(''),kind=ref('phone'),contact=ref(''),registered=ref(false),consent=ref(false)
async function call(body?:object){
 const r=await fetch(`/api/public/v1/invitations/${encodeURIComponent(token)}/`,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'omit'})
 const j=await r.json();if(!r.ok)throw new Error(typeof j.msg==='string'?j.msg:typeof j.detail==='string'?j.detail:JSON.stringify(j))
 return j.data
}
onMounted(async()=>{if(!token)return;loading.value=true;try{campaign.value=await call()}catch(e){error.value=String(e)}finally{loading.value=false}})
async function submit(){if(busy.value||!consent.value)return;busy.value=true;error.value='';try{const result=await call({contact_kind:kind.value,contact:contact.value});const url=new URL(result.download_url);if(url.protocol!=='https:'||url.hostname!=='apps.apple.com')throw new Error('下载地址暂不可用');registered.value=true;contact.value='';window.location.assign(url.href)}catch(e){error.value=String(e)}finally{busy.value=false}}
</script>
<style scoped>
.invite-page{min-height:100dvh;background:#fff8ee;color:#342b26;font:17px/1.7 system-ui;padding:24px;box-sizing:border-box}.invite-page article{max-width:520px;margin:32px auto}.brand{color:#a95330;font-weight:700;letter-spacing:.12em}h1{font-size:32px;line-height:1.3}.rules{white-space:pre-line;background:white;padding:20px;border-radius:16px;margin:24px 0}label{display:block;margin:16px 0}input:not([type=checkbox]),select{display:block;box-sizing:border-box;width:100%;padding:14px;border:1px solid #bba99b;border-radius:10px;font:inherit;background:white}button,.download{display:block;box-sizing:border-box;width:100%;padding:15px;border:0;border-radius:30px;background:#9b4428;color:white;text-align:center;font:inherit;text-decoration:none}button:disabled{opacity:.5}.small,.agree{font-size:13px}.error{color:#a52020}a{color:#8c3b24}
</style>
