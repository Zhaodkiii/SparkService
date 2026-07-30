<template>
  <a-drawer :open="open" :title="title" width="720" @close="emit('close')">
    <template v-if="detail">
      <a-descriptions bordered size="small" :column="1" title="基础字段">
        <a-descriptions-item v-for="(value, key) in detail.parsed" :key="String(key)" :label="String(key)">
          <pre class="detail-pre">{{ formatParsedField(String(key), value) }}</pre>
        </a-descriptions-item>
      </a-descriptions>

      <a-divider />
      <h4>日志原文</h4>
      <pre class="detail-pre raw-block">{{ displayRaw(detail.raw) }}</pre>

      <div v-if="detail.related_query?.request_id" style="margin-top: 16px">
        <a-button type="primary" @click="emit('jump-request', detail.related_query.request_id)">
          查看同 request_id 日志
        </a-button>
      </div>
    </template>
    <a-spin v-else :spinning="loading" />
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { SystemLogDetail } from '../../api/modules/audit';
import { formatDateTime } from '../../utils/datetime';

const props = defineProps<{
  open: boolean;
  loading: boolean;
  detail: SystemLogDetail | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'jump-request', requestId: string): void;
}>();

const title = computed(() => {
  if (!props.detail) return '日志详情';
  return `日志详情 #${props.detail.line_no}`;
});

function formatParsedField(key: string, value: unknown) {
  if (value === null || value === undefined) return '';
  if (key === 'timestamp') return formatDateTime(String(value));
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function displayRaw(value: unknown) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}
</script>

<style scoped>
.detail-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}
.raw-block {
  max-height: 420px;
  overflow: auto;
  background: #fafafa;
  padding: 12px;
  border-radius: 6px;
}
</style>
