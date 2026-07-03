<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { attachmentDisplayName, loadShareCase, type ShareAttachment, type ShareCasePayload, type ShareTimelineEvent } from '../api';

const route = useRoute();
const router = useRouter();

const payload = ref<ShareCasePayload | null>(null);
const loading = ref(false);
const errored = ref(false);
const errorTitle = ref('链接已失效');
const errorDescription = ref('请下载 App 继续查看完整医疗档案。');

const shareCode = computed(() => String(route.params.shareCode ?? 'invalid'));
const shareTitle = computed(() => payload.value?.case.title || '病例分享');
const shareExpires = computed(() => payload.value?.share.expires_at || '');
const downloadUrl = computed(() => payload.value?.download_app.url || 'https://apps.apple.com/cn/app/id6751417431');

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

function joinText(values: Array<string | undefined | null>) {
  return values
    .map((value) => value?.trim())
    .filter((value): value is string => Boolean(value))
    .join(' · ');
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

function kindTitle(kind: ShareTimelineEvent['kind']) {
  switch (kind) {
    case 'prescription':
      return '处方';
    case 'medication':
      return '服药计划';
    case 'examination':
      return '检查报告';
    case 'symptom':
      return '症状记录';
    case 'visit':
      return '就诊信息';
    case 'surgery':
      return '手术记录';
    case 'follow_up':
      return '随访记录';
    case 'meta':
      return '病例信息';
    default:
      return '记录';
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

function openEventDetail(event: ShareTimelineEvent) {
  if (event.kind === 'meta') return;
  router.replace({
    query: {
      ...route.query,
      detail: event.id,
    },
  });
}

function closeEventDetail() {
  const nextQuery = { ...route.query };
  delete nextQuery.detail;
  router.replace({ query: nextQuery });
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
const selectedEventId = computed(() => String(route.query.detail ?? ''));
const selectedEvent = computed(() => timeline.value.find((event) => event.id === selectedEventId.value) ?? null);

watch(
  selectedEvent,
  (event) => {
    document.body.style.overflow = event ? 'hidden' : '';
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  document.body.style.overflow = '';
});
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
                v-for="(attachment, index) in caseAttachments"
                :key="attachment.id"
                class="attachment-pill"
                href="#"
                @click.prevent="openAttachment(attachment)"
              >
                <span class="attachment-icon">⤓</span>
                <span class="attachment-name">{{ attachmentDisplayName(index) }}</span>
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

          <article
            v-for="event in timeline"
            :key="event.id"
            class="timeline-row timeline-row-clickable"
            role="button"
            tabindex="0"
            @click="openEventDetail(event)"
            @keydown.enter.prevent="openEventDetail(event)"
            @keydown.space.prevent="openEventDetail(event)"
          >
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

              <div v-if="event.kind === 'prescription' && event.nested_medication_plans?.length" class="nested-plans">
                <div v-for="plan in event.nested_medication_plans" :key="plan.id" class="nested-plan">
                  <strong>{{ plan.drug_name || '未命名药品' }}</strong>
                  <span>{{ plan.dose_per_time || '—' }} · {{ plan.frequency_text || '—' }}</span>
                </div>
              </div>

              <div v-if="event.attachments?.length" class="timeline-attachments">
                <a
                  v-for="(attachment, index) in event.attachments"
                  :key="attachment.id"
                  class="attachment-pill attachment-pill-inline"
                  href="#"
                  @click.stop.prevent="openAttachment(attachment)"
                >
                  <span class="attachment-icon">⤓</span>
                  <span class="attachment-name">{{ attachmentDisplayName(index) }}</span>
                </a>
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

    <transition name="fade">
      <section v-if="selectedEvent && payload" class="detail-overlay" @click.self="closeEventDetail">
        <article class="detail-sheet" :class="kindClass(selectedEvent.kind)">
          <header class="detail-sheet-header">
            <div class="detail-heading">
              <p class="eyebrow">{{ kindTitle(selectedEvent.kind) }}</p>
              <h2>{{ selectedEvent.title }}</h2>
              <p class="subtle">{{ formatDate(selectedEvent.date) }}</p>
            </div>
            <button class="icon-button" type="button" aria-label="关闭详情" @click="closeEventDetail">×</button>
          </header>

          <div class="detail-hero">
            <span class="detail-kind-chip" :class="kindClass(selectedEvent.kind)">{{ kindLabel(selectedEvent.kind) }}</span>
            <span v-if="selectedEvent.status_badge_text" class="status-chip">{{ selectedEvent.status_badge_text }}</span>
          </div>

          <div class="detail-scroll">
            <section class="detail-section">
              <p class="detail-lead">{{ selectedEvent.detail || '暂无补充说明' }}</p>
            </section>

            <section v-if="selectedEvent.kind === 'prescription' && selectedEvent.prescription" class="detail-section">
              <div class="section-head">
                <h3>处方信息</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>处方标题</span>
                  <strong>{{ selectedEvent.prescription.title }}</strong>
                </div>
                <div class="detail-field">
                  <span>开方时间</span>
                  <strong>{{ formatDate(selectedEvent.prescription.prescribed_at) || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>处方状态</span>
                  <strong>{{ selectedEvent.prescription.status || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>处方说明</span>
                  <strong>{{ selectedEvent.prescription.diagnosis || '—' }}</strong>
                </div>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'prescription' && selectedEvent.nested_medication_plans?.length" class="detail-section">
              <div class="section-head">
                <h3>服药计划</h3>
                <p>{{ selectedEvent.nested_medication_plans.length }} 项</p>
              </div>
              <div class="nested-detail-grid">
                <article v-for="plan in selectedEvent.nested_medication_plans" :key="plan.id" class="nested-plan nested-plan-detail">
                  <strong>{{ plan.drug_name || '未命名药品' }}</strong>
                  <span>{{ joinText([plan.dose_per_time, plan.frequency_text]) || '暂无剂量与频次' }}</span>
                  <span v-if="plan.box_name">药箱：{{ plan.box_name }}</span>
                  <span v-if="plan.start_date">开始：{{ formatDay(plan.start_date) }}</span>
                  <span v-if="plan.status">状态：{{ plan.status }}</span>
                </article>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'medication' && selectedEvent.medication_plan" class="detail-section">
              <div class="section-head">
                <h3>服药计划详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>药品名称</span>
                  <strong>{{ selectedEvent.medication_plan.drug_name || '未命名药品' }}</strong>
                </div>
                <div class="detail-field">
                  <span>单次剂量</span>
                  <strong>{{ selectedEvent.medication_plan.dose_per_time || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>频次</span>
                  <strong>{{ selectedEvent.medication_plan.frequency_text || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>开始日期</span>
                  <strong>{{ formatDay(selectedEvent.medication_plan.start_date) || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>状态</span>
                  <strong>{{ selectedEvent.medication_plan.status || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>药箱</span>
                  <strong>{{ selectedEvent.medication_plan.box_name || '—' }}</strong>
                </div>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'examination' && selectedEvent.examination" class="detail-section">
              <div class="section-head">
                <h3>检查详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>检查分类</span>
                  <strong>{{ selectedEvent.examination.category || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>检查子类</span>
                  <strong>{{ selectedEvent.examination.sub_category || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>项目名称</span>
                  <strong>{{ selectedEvent.examination.item_name || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>检查时间</span>
                  <strong>{{ formatDate(selectedEvent.examination.reported_at || selectedEvent.examination.performed_at) || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>分类汇总</span>
                  <strong>{{ joinText([selectedEvent.examination.category, selectedEvent.examination.sub_category]) || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>状态</span>
                  <strong>{{ selectedEvent.examination.status ?? '—' }}</strong>
                </div>
              </div>
              <div class="detail-block">
                <span>结论</span>
                <p>{{ selectedEvent.examination.impression || selectedEvent.examination.findings || '—' }}</p>
              </div>
              <div class="detail-block">
                <span>详情</span>
                <p>{{ selectedEvent.examination.findings || '—' }}</p>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'symptom' && selectedEvent.symptom" class="detail-section">
              <div class="section-head">
                <h3>症状详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>症状名称</span>
                  <strong>{{ selectedEvent.symptom.name || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>严重程度</span>
                  <strong>{{ selectedEvent.symptom.severity || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>部位</span>
                  <strong>{{ selectedEvent.symptom.body_part || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>开始时间</span>
                  <strong>{{ formatDate(selectedEvent.symptom.started_at) || '—' }}</strong>
                </div>
              </div>
              <div class="detail-block">
                <span>备注</span>
                <p>{{ selectedEvent.symptom.notes || '—' }}</p>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'visit' && selectedEvent.visit" class="detail-section">
              <div class="section-head">
                <h3>就诊详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>就诊类型</span>
                  <strong>{{ selectedEvent.visit.visit_type || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>科室</span>
                  <strong>{{ selectedEvent.visit.department || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>医生</span>
                  <strong>{{ selectedEvent.visit.doctor_name || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>号源</span>
                  <strong>{{ selectedEvent.visit.visit_no || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>时间</span>
                  <strong>{{ formatDate(selectedEvent.visit.visited_at) || '—' }}</strong>
                </div>
              </div>
              <div class="detail-block">
                <span>备注</span>
                <p>{{ selectedEvent.visit.notes || '—' }}</p>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'surgery' && selectedEvent.surgery" class="detail-section">
              <div class="section-head">
                <h3>手术详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>手术名称</span>
                  <strong>{{ selectedEvent.surgery.procedure_name || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>部位</span>
                  <strong>{{ selectedEvent.surgery.site || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>主刀医生</span>
                  <strong>{{ selectedEvent.surgery.surgeon || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>时间</span>
                  <strong>{{ formatDate(selectedEvent.surgery.performed_at) || '—' }}</strong>
                </div>
              </div>
              <div class="detail-block">
                <span>备注</span>
                <p>{{ selectedEvent.surgery.notes || '—' }}</p>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'follow_up' && selectedEvent.follow_up" class="detail-section">
              <div class="section-head">
                <h3>随访详情</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>随访方式</span>
                  <strong>{{ selectedEvent.follow_up.method || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>状态</span>
                  <strong>{{ selectedEvent.follow_up.status || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>计划时间</span>
                  <strong>{{ formatDate(selectedEvent.follow_up.planned_at) || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>完成时间</span>
                  <strong>{{ formatDate(selectedEvent.follow_up.completed_at) || '—' }}</strong>
                </div>
              </div>
              <div class="detail-block">
                <span>结果</span>
                <p>{{ selectedEvent.follow_up.outcome || '—' }}</p>
              </div>
              <div class="detail-block">
                <span>下一步</span>
                <p>{{ selectedEvent.follow_up.next_action || '—' }}</p>
              </div>
            </section>

            <section v-if="selectedEvent.kind === 'meta'" class="detail-section">
              <div class="section-head">
                <h3>病例信息</h3>
              </div>
              <div class="detail-grid">
                <div class="detail-field">
                  <span>病例名称</span>
                  <strong>{{ payload.case.title }}</strong>
                </div>
                <div class="detail-field">
                  <span>类型</span>
                  <strong>{{ payload.case.record_type || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>医院</span>
                  <strong>{{ payload.case.hospital_name || '—' }}</strong>
                </div>
                <div class="detail-field">
                  <span>更新时间</span>
                  <strong>{{ formatDate(payload.case.updated_at || payload.case.created_at) || '—' }}</strong>
                </div>
              </div>
            </section>

            <section v-if="selectedEvent.attachments?.length" class="detail-section">
              <div class="section-head">
                <h3>附件</h3>
                <p>{{ selectedEvent.attachments.length }} 个</p>
              </div>
              <div class="attachment-strip detail-attachments">
                <a
                  v-for="(attachment, index) in selectedEvent.attachments"
                  :key="attachment.id"
                  class="attachment-pill attachment-pill-inline"
                  href="#"
                  @click.prevent="openAttachment(attachment)"
                >
                  <span class="attachment-icon">⤓</span>
                  <span class="attachment-name">{{ attachmentDisplayName(index) }}</span>
                </a>
              </div>
            </section>
          </div>
        </article>
      </section>
    </transition>
  </div>
</template>
