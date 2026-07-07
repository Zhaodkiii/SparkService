<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useDocumentMeta } from '../../../shared/composables/useDocumentMeta';
import { fetchSharePayload } from '../api/shareApi';
import ShareDetailContent from '../components/ShareDetailContent.vue';
import ShareDetailSheet from '../components/ShareDetailSheet.vue';
import ShareDownloadPanel from '../components/ShareDownloadPanel.vue';
import ShareErrorState from '../components/ShareErrorState.vue';
import ShareHeader from '../components/ShareHeader.vue';
import ShareResourceSummary from '../components/ShareResourceSummary.vue';
import ShareTimeline from '../components/ShareTimeline.vue';
import type { ShareCasePayload, ShareErrorKind, SharePublicPayload, ShareTimelineEvent } from '../types';
import {
  asCasePayload,
  asNonCasePayload,
  classifyShareError,
  isBusinessType,
  resourceKindLabel,
} from '../utils';

const route = useRoute();
const router = useRouter();
const { updateMeta } = useDocumentMeta();

const payload = ref<SharePublicPayload | null>(null);
const loading = ref(false);
const errorKind = ref<ShareErrorKind | null>(null);
const errorTitle = ref('链接已失效');
const errorDescription = ref('请下载 App 继续查看完整医疗档案。');

const shareCode = computed(() => String(route.params.code ?? ''));
const isMedicalCase = computed(() => payload.value && isBusinessType(payload.value, 'medical_case'));
const casePayload = computed((): ShareCasePayload | null =>
  payload.value ? asCasePayload(payload.value) : null,
);
const nonCasePayload = computed(() => (payload.value ? asNonCasePayload(payload.value) : null));
const timeline = computed(() => casePayload.value?.timeline ?? []);
const selectedEventId = computed(() => String(route.query.detail ?? ''));
const selectedEvent = computed<ShareTimelineEvent | null>(() =>
  timeline.value.find((event: ShareTimelineEvent) => event.id === selectedEventId.value) ?? null,
);
const downloadUrl = computed(
  () =>
    payload.value?.download_app.url ||
    import.meta.env.VITE_APP_DOWNLOAD_URL ||
    'https://apps.apple.com/cn/app/id6751417431',
);

function openDownloadApp() {
  window.location.href = downloadUrl.value;
}

function openEventDetail(event: ShareTimelineEvent) {
  if (event.kind === 'meta') return;
  router.replace({ query: { ...route.query, detail: event.id } });
}

function closeEventDetail() {
  const nextQuery = { ...route.query };
  delete nextQuery.detail;
  router.replace({ query: nextQuery });
}

async function load() {
  if (!shareCode.value || shareCode.value === 'invalid') {
    errorKind.value = 'unavailable';
    errorTitle.value = '内容不可用';
    errorDescription.value = '当前分享无法打开，请下载 App 查看完整内容。';
    payload.value = null;
    return;
  }

  loading.value = true;
  errorKind.value = null;
  payload.value = null;

  try {
    const data = await fetchSharePayload(shareCode.value);
    payload.value = data;
    updateMeta({
      title: data.share.title,
      description: `${data.member.display_name} · ${resourceKindLabel(data.share.business_type)}`,
      url: typeof window !== 'undefined' ? window.location.href : undefined,
    });
  } catch (err) {
    const classified = classifyShareError(err);
    errorKind.value = classified.kind;
    errorTitle.value = classified.title;
    errorDescription.value = classified.description;
    payload.value = null;
  } finally {
    loading.value = false;
  }
}

watch(shareCode, load, { immediate: true });
</script>

<template>
  <div class="share-module">
    <div class="page-shell">
      <ShareHeader
        v-if="payload"
        :title="payload.share.title"
        :member-name="payload.member.display_name"
        :download-url="downloadUrl"
      />
      <header v-else class="top-bar">
        <div class="brand-mark">S</div>
        <div class="top-copy">
          <p class="eyebrow">Medical Share</p>
          <h1>医疗分享</h1>
          <p class="subtle">公开分享</p>
        </div>
        <a class="download-link" :href="downloadUrl">下载 App</a>
      </header>

      <main class="content-shell">
        <ShareErrorState
          v-if="loading || errorKind"
          :kind="loading ? 'loading' : errorKind!"
          :title="errorTitle"
          :description="errorDescription"
          @download="openDownloadApp"
        />

        <template v-else-if="payload">
          <ShareResourceSummary :payload="payload" />

          <ShareTimeline
            v-if="isMedicalCase"
            :timeline="timeline"
            @open-event="openEventDetail"
          />

          <ShareDetailContent v-else mode="resource" :resource-payload="nonCasePayload" />

          <ShareDownloadPanel
            :title="payload.download_app.title"
            :description="payload.download_app.description"
            :button-text="payload.download_app.button_text"
            @download="openDownloadApp"
          />
        </template>
      </main>

      <ShareDetailSheet
        v-if="isMedicalCase"
        :visible="Boolean(selectedEvent)"
        :event="selectedEvent"
        :case-payload="casePayload"
        @close="closeEventDetail"
      />
    </div>
  </div>
</template>

<style src="../../../shared/styles/share-content.css"></style>
