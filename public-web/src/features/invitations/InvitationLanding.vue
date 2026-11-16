<template>
  <main class="invite-page">
    <header class="masthead"><a href="/" class="brand"><img class="brand-logo" :src="brandLogo" alt="" width="44" height="44" /><span>寻寻仔<small>旅行手帐</small></span></a><span class="header-note">一份来自好友的邀请</span></header>
    <div class="invite-layout">
      <section class="intro" aria-labelledby="invite-title">
        <p class="eyebrow">GOOD TRIPS, TOGETHER</p>
        <h1 id="invite-title">好风景，<br>一起留在手帐里。</h1>
        <p class="intro-copy">好友邀请你加入寻寻仔。<br>把旅途中的小美好，收藏成一本旅行手帐。</p>
        <img class="hero-art" :src="travelJournal" alt="实拍手帐素材衍生展示" width="900" height="600" fetchpriority="high" />
        <p class="art-caption">实拍素材衍生展示 · 让每一次出发，都有迹可循。</p>
      </section>
      <div class="action-column">
        <section class="registration-card" aria-labelledby="form-title" :aria-busy="loading">
          <p class="section-kicker">FRIEND INVITATION <span>好友邀请</span></p>
          <template v-if="loading"><h2 id="form-title">正在打开邀请…</h2><p role="status" class="muted">旅途的下一页，马上开始。</p></template>
          <template v-else-if="registered">
            <span class="success-mark" aria-hidden="true">✓</span><h2 id="form-title" tabindex="-1" ref="successHeading">登记成功，旅途见！</h2>
            <p class="muted">接下来下载寻寻仔，在 {{campaign?.attribution_days || 7}} 天内使用刚才验证的{{kind==='phone'?'手机号登录或绑定':'邮箱绑定账号'}}，即可确认好友邀请。请在活动结束前完成。</p>
            <p class="muted">登记账号：{{registeredContact}}<br>请在 {{registrationDeadline}} 前完成 App 验证。</p><p class="muted">已安装 App？直接打开寻寻仔，用登记手机号登录或绑定；邮箱用户请在账号设置验证绑定相同邮箱。</p>
            <a class="primary download" :href="downloadUrl">前往 App Store 下载 <span aria-hidden="true">↗</span></a>
            <p class="privacy-note">登记不会自动创建账号，也不会立即发放奖励。</p>
          </template>
          <template v-else-if="campaign?.available">
            <h2 id="form-title">接受好友邀请</h2><p class="muted form-intro">验证联系方式，开启你的旅行手帐。</p>
            <form @submit.prevent="submit">
              <div class="method-switch" role="group" aria-label="选择登记方式"><button type="button" :aria-pressed="kind==='phone'" :class="{active:kind==='phone'}" :disabled="busy" @click="setKind('phone')">手机号登记</button><button type="button" :aria-pressed="kind==='email'" :class="{active:kind==='email'}" :disabled="busy" @click="setKind('email')">邮箱登记</button></div>
              <label for="invite-contact">{{kind==='phone'?'手机号':'邮箱地址'}}</label>
              <div class="contact-input"><span v-if="kind==='phone'" class="dial-code">+86</span><input id="invite-contact" v-model="contact" :type="kind==='phone'?'tel':'email'" :autocomplete="kind==='phone'?'tel-national':'email'" :placeholder="kind==='phone'?'请输入手机号':'请输入你的邮箱地址'" :maxlength="kind==='phone'?11:254" required :disabled="busy" @input="invalidateCode" /></div>
              <label for="invite-code">验证码</label>
              <div class="code-input"><input id="invite-code" ref="codeInput" v-model="code" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位数字验证码" pattern="[0-9]{6}" maxlength="6" required :disabled="busy"/><button type="button" class="send-code" :disabled="busy || cooldown>0 || !contactValid || !consent" @click="sendCode">{{sending?'发送中…':cooldown>0?`${cooldown}s 后重发`:challengeId?'重新发送':'获取验证码'}}</button></div>
              <p class="delivery-note" role="status">{{notice || (kind==='phone'?'验证码将通过短信发送至你的手机。':'验证码将发送至邮箱，也请留意垃圾邮件。')}}</p>
              <label class="consent"><input v-model="consent" type="checkbox" :disabled="busy" required/><span>我已阅读并同意<button type="button" class="text-link" @click="showRules">活动规则</button>及<a href="https://www.dreamwhale.top/legal/privacy/" target="_blank" rel="noopener">隐私政策</a></span></label>
              <p v-if="error" role="alert" class="error">{{error}}</p>
              <button class="primary" :disabled="busy || !consent || !challengeId || !/^\d{6}$/.test(code)" type="submit">{{submitting?'正在验证…':'验证并接受邀请'}}<span v-if="!submitting" aria-hidden="true">→</span></button>
              <p class="privacy-note">联系方式仅用于验证及匹配邀请，不会展示给好友。</p>
            </form>
          </template>
          <template v-else><h2 id="form-title">{{campaign?'这份邀请暂不可用':'暂时无法打开邀请'}}</h2><p class="muted" role="status">{{campaign?'活动已结束或暂停，当前无法登记。你仍可查看下方产品介绍和活动规则。':error || '请通过好友分享的完整邀请链接进入。'}}</p><button v-if="token && !campaign" type="button" class="primary" @click="load">重新加载</button></template>
        </section>
        <ol v-if="campaign" class="steps" aria-label="参与步骤"><li><b>01</b><span>验证并登记</span></li><li><b>02</b><span>下载寻寻仔</span></li><li><b>03</b><span>App 内登录或绑定</span></li></ol>
      </div>
    </div>
    <section v-if="campaign" class="campaign-info">
      <div class="campaign-heading"><div><p class="eyebrow">MAKE MEMORIES</p><h2>和好友一起，收获更多美好</h2></div><span class="deadline">截至 {{deadline}}（北京时间）</span></div>
      <p class="reward-note">标准装订券不含运费、超页及升级费用，适用范围与抵扣上限见活动规则。</p>
      <p class="reward-note">以下为邀请人奖励，需新用户在 App 内完成验证后计入。</p>
      <div class="rewards"><div v-if="campaign.cards_per_invite"><span class="reward-number">01<span>位好友</span></span><strong>{{campaign.cards_per_invite}} 张制作额度重置卡</strong><p>每人最多奖励 {{campaign.card_invite_limit}} 次</p></div><div><span class="reward-number">05<span>位好友</span></span><strong>A5 标准装订半价券</strong><p>把旅行记忆，翻成纸上的风景</p></div><div><span class="reward-number">10<span>位好友</span></span><strong>A5 标准装订免费券</strong><p>珍藏一路上的每个瞬间</p></div></div>
      <details ref="rulesElement" class="rules"><summary>活动规则与奖励说明<span aria-hidden="true">＋</span></summary><p>{{campaign.rules}}</p><p>请在登记后 {{campaign.attribution_days || 7}} 天内、且活动结束前，在 App 内验证相同联系方式。登记成功不代表邀请已确认。</p></details>
    </section>
    <footer>寻寻仔 · 旅行手帐<span>把旅途，留在身边。</span></footer>
  </main>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onUnmounted,nextTick} from 'vue'
import {useRoute} from 'vue-router'
import travelJournal from '../../assets/invitation/journal-real-v3.jpg'
import brandLogo from '../../assets/invitation/xunxunzi-logo.png'
type Kind='phone'|'email'
type Campaign={title:string;rules:string;ends_at:string;available:boolean;download_url:string;attribution_days:number;cards_per_invite:number;card_invite_limit:number}
const token=String(useRoute().params.token||'')
const campaign=ref<Campaign>(),loading=ref(false),sending=ref(false),submitting=ref(false),error=ref(''),notice=ref(''),kind=ref<Kind>('phone'),contact=ref(''),code=ref(''),challengeId=ref(''),registered=ref(false),consent=ref(false),cooldown=ref(0),downloadUrl=ref('')
const registeredContact=ref(''),registrationDeadline=ref('')
const codeInput=ref<HTMLInputElement>(),rulesElement=ref<HTMLDetailsElement>(),successHeading=ref<HTMLElement>()
const busy=computed(()=>sending.value||submitting.value)
const contactValid=computed(()=>kind.value==='phone'?/^1[3-9]\d{9}$/.test(contact.value.trim()):/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact.value.trim()))
const deadline=computed(()=>campaign.value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(campaign.value.ends_at)):'')
let resendAt=0
const timer=setInterval(()=>{cooldown.value=Math.max(0,Math.ceil((resendAt-Date.now())/1000))},250)
onUnmounted(()=>clearInterval(timer))
function invalidateCode(){challengeId.value='';code.value='';notice.value='';error.value=''}
function setKind(value:Kind){if(kind.value===value)return;kind.value=value;contact.value='';invalidateCode()}
async function showRules(){if(rulesElement.value){rulesElement.value.open=true;await nextTick();rulesElement.value.scrollIntoView({behavior:'smooth',block:'center'})}}
function message(value:unknown):string{if(typeof value==='string')return value;if(Array.isArray(value))return value.map(message).join('；');if(value&&typeof value==='object')return Object.values(value).map(message).join('；');return '操作未完成，请稍后重试'}
async function call(body?:object,suffix=''){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000)
 try{const r=await fetch(`/api/public/v1/invitations/${encodeURIComponent(token)}/${suffix}`,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'omit',signal:controller.signal})
 const j=await r.json();if(!r.ok){if(r.status===429){const wait=Number(r.headers.get('Retry-After'));if(Number.isFinite(wait)&&wait>0){resendAt=Date.now()+wait*1000;cooldown.value=wait}}throw new Error(message(j.detail||j.errors||j.msg||j))}return j.data
 }catch(e){if(e instanceof Error&&e.name==='AbortError')throw new Error('连接超时，请稍后重试');throw e}finally{clearTimeout(timeout)}
}
async function load(){document.title='好友邀请 · 寻寻仔旅行手帐';if(!token)return;loading.value=true;error.value='';try{campaign.value=await call()}catch(e){error.value=e instanceof Error?e.message:'邀请加载失败，请重试'}finally{loading.value=false}}
onMounted(load)
async function sendCode(){if(busy.value||cooldown.value||!consent.value||!contactValid.value)return;sending.value=true;error.value='';try{const result=await call({contact_kind:kind.value,contact:contact.value.trim(),consent:consent.value},'code/');challengeId.value=result.challenge_id;code.value='';resendAt=Date.now()+result.resend_after*1000;cooldown.value=result.resend_after;notice.value=kind.value==='phone'?'验证码已发送，5 分钟内有效。':'邮件已发送，验证码 5 分钟内有效。';}catch(e){error.value=e instanceof Error?e.message:'验证码发送失败，请重试'}finally{sending.value=false;await nextTick();if(!error.value)codeInput.value?.focus()}}
async function submit(){if(busy.value||!consent.value||!challengeId.value)return;submitting.value=true;error.value='';try{const result=await call({contact_kind:kind.value,contact:contact.value.trim(),challenge_id:challengeId.value,code:code.value,consent:consent.value});const url=new URL(result.download_url);if(url.protocol!=='https:'||url.hostname!=='apps.apple.com')throw new Error('下载地址暂不可用');downloadUrl.value=url.href;const value=contact.value.trim();registeredContact.value=kind.value==='phone'?value.slice(0,3)+'****'+value.slice(-4):value.slice(0,1)+'***@'+value.split('@')[1];const expiry=result.expires_at||campaign.value?.ends_at;registrationDeadline.value=expiry?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',dateStyle:'medium',timeStyle:'short'}).format(new Date(expiry))+'（北京时间）':'活动规定期限';registered.value=true;contact.value='';code.value='';await nextTick();successHeading.value?.focus()}catch(e){error.value=e instanceof Error?e.message:'登记失败，请重试'}finally{submitting.value=false}}
</script>
<style scoped>
.invite-page{--paper:#faf8f4;--ink:#302f29;--muted:#77766d;--accent:#a45036;min-height:100dvh;background:var(--paper);color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;padding:0 40px;box-sizing:border-box}.invite-page *{box-sizing:border-box}.masthead{max-width:1080px;margin:auto;padding:30px 0;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e9e5dd}.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);font-size:19px;font-weight:650;letter-spacing:1px}.brand-logo{width:44px;height:44px;object-fit:contain;border-radius:10px}.brand small{font-size:10px;display:block;letter-spacing:3px;font-weight:400;color:var(--muted)}.brand-mark{display:grid;place-items:center;width:40px;height:43px;border:1.5px solid var(--accent);border-radius:11px 11px 11px 3px;color:var(--accent);font-family:serif;font-size:25px}.header-note{font-size:12px;color:var(--muted)}.invite-layout{max-width:1000px;display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:70px;margin:58px auto 42px;align-items:start}.eyebrow{font-size:10px;letter-spacing:2.4px;color:var(--accent);font-weight:600;margin:0 0 16px}h1{font-size:48px;line-height:1.35;letter-spacing:-1.5px;margin:0 0 20px;font-weight:650}.intro-copy{color:var(--muted);font-size:15px;line-height:1.9;margin:0}.hero-art{display:block;width:100%;height:auto;max-height:280px;object-fit:contain;margin:14px 0 0;mix-blend-mode:multiply}.art-caption{color:#88867a;font-size:11px;letter-spacing:2px;text-align:center;margin:0}.registration-card{padding:30px;background:#fff;border:1px solid #ece8df;border-radius:20px;box-shadow:0 12px 45px #45332006}.section-kicker{font-size:9px;color:#99958c;letter-spacing:1.6px;display:flex;justify-content:space-between;margin:0 0 22px}.section-kicker span{letter-spacing:1px;color:var(--accent)}h2{font-size:24px;line-height:1.4;margin:0 0 9px;font-weight:600;letter-spacing:-.5px}.muted{color:var(--muted);font-size:13px}.form-intro{margin:0 0 23px}.method-switch{display:flex;background:#f5f4f0;border-radius:10px;padding:4px;margin-bottom:22px}.method-switch button{flex:1;border:0;background:transparent;border-radius:7px;padding:9px;color:var(--muted);font-size:13px}.method-switch button.active{background:white;color:var(--ink);box-shadow:0 2px 5px #302f2910}label:not(.consent){display:block;font-size:12px;margin:15px 0 7px;font-weight:550}.contact-input,.code-input{display:flex;align-items:center;border:1px solid #e3e0d8;border-radius:9px;height:48px;background:#fff}.contact-input:focus-within,.code-input:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px #a4503610}.dial-code{padding:0 13px;border-right:1px solid #e6e3dc;font-size:13px}input:not([type=checkbox]){width:100%;min-width:0;border:0;background:transparent;padding:12px;font:inherit;color:var(--ink);outline:0}input::placeholder{color:#a19e94;font-size:13px}.send-code{flex-shrink:0;background:none;border:0;border-left:1px solid #e6e3dc;padding:0 13px;font-size:12px;color:var(--accent)}button{font-family:inherit;cursor:pointer}button:disabled{cursor:not-allowed;color:#aaa79e}.delivery-note{font-size:11px;color:var(--muted);min-height:18px;margin:8px 0 19px}.consent{display:flex;gap:8px;align-items:flex-start;font-size:11px;color:var(--muted);margin:0 0 18px}.consent input{width:15px;height:15px;flex-shrink:0;accent-color:var(--accent);margin:2px 0}.text-link,.consent a{color:#6e6554;text-decoration:underline;text-underline-offset:3px}.text-link{border:0;background:none;font:inherit;padding:0 2px}.primary{display:flex;justify-content:center;align-items:center;gap:20px;background:var(--accent);color:#fff;width:100%;border:0;border-radius:10px;min-height:48px;font-size:14px;font-weight:550;text-decoration:none;transition:background .15s}.primary:hover:not(:disabled){background:#88412c}.primary:disabled{background:#ece8e0;color:#969184}.privacy-note{font-size:10px;color:#8a887e;margin:13px 0 0;text-align:center}.error{padding:10px 12px;background:#fff2ed;color:#a23c27;border-radius:7px;font-size:12px}.steps{list-style:none;display:flex;padding:0;justify-content:space-between;margin:20px 8px 0;gap:10px;color:var(--muted);font-size:10px}.steps li{display:flex;align-items:center;gap:6px}.steps b{font-size:10px;font-weight:400;color:var(--accent)}.campaign-info{max-width:1000px;margin:0 auto;border-top:1px solid #e6e2d9;padding:30px 0 0}.campaign-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.campaign-heading h2{font-size:20px}.campaign-heading .eyebrow{font-size:9px;margin-bottom:6px}.deadline{font-size:10px;color:var(--muted)}.reward-note{font-size:11px;color:var(--muted);margin:3px 0 22px}.rewards{display:grid;grid-template-columns:repeat(3,1fr);gap:30px;margin-bottom:28px}.rewards>div{border-left:1px solid #ded9ce;padding:0 20px}.reward-number{display:block;font-size:29px;font-weight:400;color:#6e7560;line-height:1.2;margin-bottom:12px}.reward-number span{font-size:10px;color:var(--muted);padding-left:6px}.rewards strong{font-size:13px;font-weight:550}.rewards p{font-size:11px;color:var(--muted);margin:4px 0}.rules{border-top:1px solid #e6e2d9;border-bottom:1px solid #e6e2d9;font-size:12px;color:var(--muted)}summary{cursor:pointer;padding:18px 0;color:#5f5b50;display:flex;justify-content:space-between;list-style:none}summary::-webkit-details-marker{display:none}.rules[open] summary span{transform:rotate(45deg)}.rules p{white-space:pre-line;line-height:1.9;margin:0 0 20px;max-width:790px}footer{max-width:1000px;margin:auto;display:flex;justify-content:space-between;padding:25px 0 30px;font-size:10px;color:#918c80}.success-mark{display:grid;place-items:center;background:#edf1e8;color:#6e7b5c;width:48px;height:48px;border-radius:50%;font-size:24px;margin-bottom:20px}.download{margin-top:25px}:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
@media(max-width:760px){.invite-page{padding:0 22px}.masthead{padding:19px 0}.header-note{font-size:10px}.brand{font-size:16px}.brand-mark{width:33px;height:36px;font-size:21px}.invite-layout{display:block;margin:30px auto 30px;max-width:440px}.intro{text-align:center}.eyebrow{font-size:9px;margin-bottom:12px}h1{font-size:34px;line-height:1.3;letter-spacing:-.5px}h1 br{display:none}.intro-copy{font-size:12px}.hero-art{height:155px;margin:3px 0 8px}.art-caption{display:none}.registration-card{padding:24px;border-radius:16px}.section-kicker{margin-bottom:16px}h2{font-size:22px}.campaign-heading{align-items:flex-start;flex-direction:column;gap:3px}.campaign-heading h2{font-size:18px}.campaign-info{padding-top:24px;max-width:440px}.reward-note{margin-top:12px}.rewards{gap:10px}.rewards>div{padding-left:10px}.reward-number{font-size:24px}.reward-number span{font-size:9px}.rewards strong{font-size:11px}.rewards p{font-size:10px}.steps{font-size:9px}footer{max-width:440px}.form-intro{margin-bottom:18px}}
@media(max-width:760px){.masthead{padding:14px 0}.invite-layout{margin-top:20px}.intro>.eyebrow{display:none}h1{font-size:28px;margin-bottom:12px}.intro-copy{line-height:1.7}.hero-art{height:100px;margin:8px 0 14px}.registration-card{padding:20px}.section-kicker{margin-bottom:12px}.form-intro{margin-bottom:16px}.method-switch{margin-bottom:14px}.delivery-note{margin-bottom:13px}.consent{margin-bottom:14px}}
input:not([type=checkbox]){font-size:16px}.send-code{min-height:44px}.delivery-note,.consent,.privacy-note{font-size:12px}.deadline{font-size:12px}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
</style>
