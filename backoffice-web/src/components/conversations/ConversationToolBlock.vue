<template>
  <div class="chat-tool-card">
    <div class="chat-card-title">
      <ToolOutlined style="margin-right: 6px" />
      {{ toolName }}
      <a-tag v-if="statusLabel" size="small" style="margin-left: 8px">{{ statusLabel }}</a-tag>
    </div>

    <div v-if="summaryText" class="chat-tool-result">{{ summaryText }}</div>

        <a-collapse v-if="hasDetail" ghost :active-key="expandedKeys">
      <a-collapse-panel key="detail" header="查看过程详情">
        <div v-if="paramsText" class="chat-tool-params">{{ paramsText }}</div>
        <div v-if="resultText" class="chat-tool-result">{{ resultText }}</div>
      </a-collapse-panel>
    </a-collapse>

    <a-button type="link" size="small" class="chat-debug-link" @click="emit('view-debug', block)">调试</a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ToolOutlined } from '@ant-design/icons-vue';
import type { ConversationBlock } from '../../api/modules/conversations';
import { readTool } from '../../utils/conversationBlockHelpers';
import { formatJson } from '../../utils/conversationRender';

const props = defineProps<{
  block: ConversationBlock;
  expanded?: boolean;
}>();

const emit = defineEmits<{ 'view-debug': [block: ConversationBlock] }>();

const expandedKeys = computed(() => (props.expanded ? ['detail'] : []));

const tool = computed(() => readTool(props.block.payload || {}));

const toolName = computed(() => tool.value.name);

const statusLabel = computed(() => {
  if (props.block.status === 'streaming') return '执行中';
  if (props.block.status === 'failed') return '失败';
  if (props.block.status === 'pending') return '等待中';
  return '';
});

function stringify(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of ['description', 'summary', 'text', 'message', 'result']) {
      const item = record[key];
      if (typeof item === 'string' && item.trim()) return item.trim();
    }
    return formatJson(value);
  }
  return value ? String(value) : '';
}

const paramsText = computed(() => stringify(tool.value.args));
const resultText = computed(() => stringify(tool.value.content));
const summaryText = computed(() => {
  if (resultText.value) {
    return resultText.value.length > 180 ? `${resultText.value.slice(0, 180)}…` : resultText.value;
  }
  if (paramsText.value) return '正在调用工具…';
  return '工具调用';
});
const hasDetail = computed(() => Boolean(paramsText.value || (resultText.value && resultText.value.length > 180)));
</script>
