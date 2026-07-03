<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { fileDisplayName, loadShareCase, type ShareAttachment, type ShareCasePayload, type ShareTimelineEvent } from '../api';

const route = useRoute();
const payload = ref<ShareCasePayload | null>(null);
const loading = ref(false);
const errored = ref(false);
const errorTitle = ref('链接已失效');
const errorDescription = ref('请下载 App 继续查看完整医疗档案。');

const shareCode = computed(() => String(route.params.shareCode ?? 'invalid'));
const shareTitle = computed(() => payload.value?.case.title || '病例分享');
const shareExpires = computed(() => payload.value?.share.expires_at || '');
const downloadUrl = computed(() => payload.value?.download_app.url || 'https://www.dreamhua.top/');

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

const dayFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

function formatDate(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return dateFormatter.format(parsed);
}

function formatDay(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return dayFormatter.format(parsed);
}

function kindLabel(kind: ShareTimelineEvent['kind']) {
  switch (kind) {
    case 'prescription':
      return '处';
    case 'medication':
      return '药';
    case 'examination':
      return '检';
    case 'symptom':
      return '症';
    case 'visit':
      return '诊';
    case 'surgery':
      return '术';
    case 'follow_up':
      return '访';
    case 'meta':
      return '信';
    default:
      return '医';
  }
}

function kindClass(kind: ShareTimelineEvent['kind']) {
  return `kind-${kind}`;
}

function openDownloadApp() {
  window.location.href = downloadUrl.value;
}

function openAttachment(file: ShareAttachment) {
  const url = file.download_url || file.file_url;
  if (!url) return;
  window.open(url, '_blank', 'noopener,noreferrer');
}

async function load() {
  loading.value = true;
  errored.value = false;
  try {
    const response = await loadShareCase(shareCode.value);
    if (response.code !== 0 || !response.data) {
      const message = String(response.msg || 'share_invalid');
      errored.value = true;
      if (message.includes('expired') || message.includes('revoked')) {
        errorTitle.value = '链接已失效';
        errorDescription.value = '分享已过期或已撤销，请下载 App 继续查看。';
      } else {
        errorTitle.value = '内容不可用';
        errorDescription.value = '当前病例分享无法打开，请下载 App 查看完整内容。';
      }
      payload.value = null;
      return;
    }
    payload.value = response.data;
  } catch {
    errored.value = true;
    errorTitle.value = '链接已失效';
    errorDescription.value = '网络不可用或链接已过期，请下载 App 查看完整内容。';
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

watch(shareCode, load, { immediate: true });

const timeline = computed(() => payload.value?.timeline ?? []);
const caseAttachments = computed(() => payload.value?.case.attachments ?? []);
</script>

<template>
  <div class="page-shell">
    <header class="top-bar">
      <div class="brand-mark">S</div>
      <div class="top-copy">
        <p class="eyebrow">Medical Share</p>
        <h1>{{ shareTitle }}</h1>
        <p class="subtle">{{ payload?.member.display_name || '病例公开分享' }}</p>
      </div>
      <a class="download-link" :href="downloadUrl">下载 App</a>
    </header>

    <main class="content-shell">
      <section v-if="loading" class="state-card">
        <div class="spinner" />
        <h2>正在加载病例</h2>
        <p>请稍候，我们正在获取公开分享内容。</p>
      </section>

      <section v-else-if="errored || !payload" class="state-card expired">
        <div class="state-badge">已失效</div>
        <h2>{{ errorTitle }}</h2>
        <p>{{ errorDescription }}</p>
        <button class="primary-button" type="button" @click="openDownloadApp">下载 App</button>
      </section>

      <template v-else>
        <section class="case-card">
          <div class="case-accent" />
          <div class="case-body">
            <div class="case-head">
              <div>
                <p class="eyebrow">病例摘要</p>
                <h2>{{ payload.case.title }}</h2>
              </div>
              <span class="status-chip">{{ payload.case.status_badge_text || '病例' }}</span>
            </div>

            <div class="case-meta">
              <span>成员：{{ payload.member.display_name }}</span>
              <span v-if="payload.member.gender">性别：{{ payload.member.gender }}</span>
              <span v-if="payload.member.age_text">{{ payload.member.age_text }}</span>
            </div>

            <div class="case-summary">
              <p v-if="payload.case.diagnosis_summary">{{ payload.case.diagnosis_summary }}</p>
              <div class="summary-line">
                <span v-if="payload.case.hospital_name">{{ payload.case.hospital_name }}</span>
                <span v-if="payload.case.record_type">{{ payload.case.record_type }}</span>
                <span v-if="payload.case.created_at">{{ formatDay(payload.case.created_at) }}</span>
              </div>
            </div>

            <div v-if="caseAttachments.length" class="attachment-strip">
              <a
                v-for="attachment in caseAttachments"
                :key="attachment.id"
                class="attachment-pill"
                href="#"
                @click.prevent="openAttachment(attachment)"
              >
                <span class="attachment-icon">⤓</span>
                <span class="attachment-name">{{ fileDisplayName(attachment) }}</span>
              </a>
            </div>

            <div class="expires-note">
              <span>分享码</span>
              <strong>{{ payload.share.share_code }}</strong>
              <span>有效至 {{ formatDate(shareExpires) }}</span>
            </div>
          </div>
        </section>

        <section class="timeline-section">
          <div class="section-head">
            <h3>时间线</h3>
            <p>{{ timeline.length }} 条记录</p>
          </div>

          <div v-if="timeline.length === 0" class="empty-timeline">
            暂无公开时间线内容
          </div>

          <article v-for="event in timeline" :key="event.id" class="timeline-row">
            <div class="timeline-icon" :class="kindClass(event.kind)">
              {{ kindLabel(event.kind) }}
            </div>
            <div class="timeline-card">
              <div class="timeline-topline">
                <span class="timeline-date">{{ formatDay(event.date) }}</span>
                <span v-if="event.status_badge_text" class="timeline-badge">{{ event.status_badge_text }}</span>
              </div>
              <h4>{{ event.title }}</h4>
              <p class="timeline-detail">{{ event.detail }}</p>

              <div v-if="event.attachments?.length" class="timeline-attachments">
                <a
                  v-for="attachment in event.attachments"
                  :key="attachment.id"
                  class="attachment-pill attachment-pill-inline"
                  href="#"
                  @click.prevent="openAttachment(attachment)"
                >
                  <span class="attachment-icon">⤓</span>
                  <span class="attachment-name">{{ fileDisplayName(attachment) }}</span>
                </a>
              </div>

              <div v-if="event.kind === 'prescription' && event.nested_medication_plans?.length" class="nested-plans">
                <div v-for="plan in event.nested_medication_plans" :key="plan.id" class="nested-plan">
                  <strong>{{ plan.drug_name }}</strong>
                  <span>{{ plan.dose_per_time || '—' }} · {{ plan.frequency_text || '—' }}</span>
                </div>
              </div>
            </div>
          </article>
        </section>

        <footer class="download-panel">
          <div>
            <h3>{{ payload.download_app.title }}</h3>
            <p>{{ payload.download_app.description }}</p>
          </div>
          <button class="primary-button" type="button" @click="openDownloadApp">
            {{ payload.download_app.button_text }}
          </button>
        </footer>
      </template>
    </main>
  </div>
</template>
