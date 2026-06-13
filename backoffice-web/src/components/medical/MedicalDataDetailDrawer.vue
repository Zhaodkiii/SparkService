<template>
  <a-drawer
    :open="open"
    :title="title"
    width="720"
    destroy-on-close
    @close="emit('update:open', false)"
  >
    <a-spin :spinning="loading">
      <template v-if="detail">
        <a-space wrap style="margin-bottom: 12px">
          <a-tag>{{ detail.resource_type }}</a-tag>
          <a-tag color="blue">#{{ detail.resource_id }}</a-tag>
        </a-space>

        <div v-if="imageAttachments.length" class="image-preview-section">
          <div class="section-title">图片预览</div>
          <a-image-preview-group>
            <div
              v-for="item in imageAttachments"
              :key="String(item.id ?? item.url)"
              :class="['preview-card', { 'preview-card--hero': isSingleAttachmentDetail }]"
            >
              <a-image
                :src="item.url"
                :alt="item.name"
                :width="isSingleAttachmentDetail ? '100%' : 120"
                :height="isSingleAttachmentDetail ? 360 : 120"
                :style="isSingleAttachmentDetail ? { maxHeight: '360px', objectFit: 'contain' } : undefined"
                class="preview-image"
                :fallback="imageFallback"
              />
              <div class="preview-meta">
                <div class="preview-name" :title="item.name">{{ item.name }}</div>
                <div class="preview-mime">{{ item.mimeType || '-' }}</div>
                <a-button
                  v-if="canDownload && item.id"
                  size="small"
                  type="link"
                  @click="downloadAttachment(item.id)"
                >
                  下载
                </a-button>
              </div>
            </div>
          </a-image-preview-group>
        </div>

        <a-descriptions bordered size="small" :column="1" title="基础信息">
          <a-descriptions-item v-for="(value, key) in scalarBasic" :key="String(key)" :label="String(key)">
            {{ formatValue(value) }}
          </a-descriptions-item>
        </a-descriptions>

        <div v-if="detail.med_exam_details?.length" style="margin-top: 16px">
          <div class="section-title">明细项</div>
          <a-table
            size="small"
            :data-source="detail.med_exam_details"
            :pagination="false"
            row-key="id"
            :scroll="{ x: 900 }"
          >
            <a-table-column title="项目" data-index="item_name" />
            <a-table-column title="结果" data-index="result_value" />
            <a-table-column title="单位" data-index="unit" :width="80" />
            <a-table-column title="参考范围" data-index="reference_range" />
            <a-table-column title="异常" data-index="flag" :width="80" />
          </a-table>
        </div>

        <div v-if="fileAttachments.length" style="margin-top: 16px">
          <div class="section-title">附件</div>
          <a-list size="small" bordered :data-source="fileAttachments">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta :title="item.name" :description="item.mimeType" />
                <template #actions>
                  <a v-if="item.url" :href="item.url" target="_blank" rel="noopener">打开</a>
                  <a-button
                    v-if="canDownload && item.id"
                    size="small"
                    type="link"
                    @click="downloadAttachment(item.id)"
                  >
                    下载
                  </a-button>
                </template>
              </a-list-item>
            </template>
          </a-list>
        </div>

        <div v-if="Object.keys(detail.ai_info || {}).length" style="margin-top: 16px">
          <div class="section-title">AI 识别信息</div>
          <a-descriptions bordered size="small" :column="1">
            <a-descriptions-item v-for="(value, key) in detail.ai_info" :key="String(key)" :label="String(key)">
              {{ formatValue(value) }}
            </a-descriptions-item>
          </a-descriptions>
        </div>

        <div v-if="Object.keys(detail.related || {}).length" style="margin-top: 16px">
          <div class="section-title">关联数据</div>
          <pre class="json-block">{{ JSON.stringify(detail.related, null, 2) }}</pre>
        </div>

        <div v-if="detail.raw_json" style="margin-top: 16px">
          <a-collapse>
            <a-collapse-panel key="raw" header="原始 JSON">
              <pre class="json-block">{{ JSON.stringify(detail.raw_json, null, 2) }}</pre>
            </a-collapse-panel>
          </a-collapse>
        </div>
      </template>
    </a-spin>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { message } from 'ant-design-vue';
import {
  fetchMedicalDataAttachmentDownload,
  type MedicalDataResourceDetail,
} from '../../api/modules/medicalData';
import { formatDateTime } from '../../utils/datetime';

interface AttachmentViewItem {
  id?: number;
  url: string;
  name: string;
  mimeType: string;
}

const props = defineProps<{
  open: boolean;
  loading: boolean;
  detail: MedicalDataResourceDetail | null;
  title: string;
  canDownload: boolean;
}>();

const emit = defineEmits<{ 'update:open': [boolean] }>();

const imageFallback =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="100%" height="100%" fill="#f5f5f5"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#999" font-size="12">不可用</text></svg>',
  );

const normalizedAttachments = computed<AttachmentViewItem[]>(() => {
  if (!props.detail) return [];

  const rows: AttachmentViewItem[] = [];
  const seen = new Set<string>();

  const pushRow = (raw: Record<string, unknown>) => {
    const url = typeof raw.file_url === 'string' ? raw.file_url.trim() : '';
    const id = typeof raw.id === 'number' ? raw.id : undefined;
    const name = typeof raw.original_name === 'string' ? raw.original_name : `附件 ${id ?? ''}`.trim();
    const mimeType = typeof raw.mime_type === 'string' ? raw.mime_type : '';
    const dedupeKey = `${id ?? ''}:${url}:${name}`;
    if (seen.has(dedupeKey)) return;
    seen.add(dedupeKey);
    rows.push({ id, url, name, mimeType });
  };

  for (const item of props.detail.attachments || []) {
    if (item && typeof item === 'object') {
      pushRow(item as Record<string, unknown>);
    }
  }

  if (props.detail.resource_type === 'attachments' && props.detail.basic) {
    pushRow(props.detail.basic);
  }

  return rows;
});

const imageAttachments = computed(() =>
  normalizedAttachments.value.filter((item) => isImageAttachment(item) && item.url),
);

const fileAttachments = computed(() =>
  normalizedAttachments.value.filter((item) => !isImageAttachment(item)),
);

const isSingleAttachmentDetail = computed(
  () => props.detail?.resource_type === 'attachments' && imageAttachments.value.length === 1,
);

const scalarBasic = computed(() => {
  if (!props.detail?.basic) return {};
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props.detail.basic)) {
    if (value !== null && typeof value !== 'object') {
      result[key] = value;
    }
  }
  return result;
});

function isImageAttachment(item: AttachmentViewItem) {
  if (item.mimeType.startsWith('image/')) return true;
  return /\.(jpg|jpeg|png|gif|webp|bmp|heic|heif)$/i.test(item.name);
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'string' && /\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatDateTime(value);
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

async function downloadAttachment(fileId: number) {
  try {
    const data = await fetchMedicalDataAttachmentDownload(fileId);
    window.open(data.url, '_blank', 'noopener');
  } catch {
    message.error('下载失败');
  }
}
</script>

<style scoped>
.section-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.image-preview-section {
  margin-bottom: 16px;
}
.image-preview-section :deep(.ant-image-preview-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.preview-card {
  width: 120px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
  background: #fafafa;
}
.preview-card--hero {
  width: 100%;
  max-width: 100%;
}
.preview-image {
  display: block;
  background: #fff;
}
.preview-card--hero :deep(.ant-image) {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #fafafa;
}
.preview-card--hero :deep(.ant-image-img) {
  width: auto !important;
  max-width: 100%;
  max-height: 360px;
  object-fit: contain;
}
.preview-meta {
  padding: 8px;
}
.preview-name {
  font-size: 12px;
  line-height: 1.4;
  word-break: break-all;
}
.preview-mime {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}
.json-block {
  background: #f6f8fa;
  padding: 12px;
  border-radius: 6px;
  overflow: auto;
  max-height: 320px;
  font-size: 12px;
}
</style>
