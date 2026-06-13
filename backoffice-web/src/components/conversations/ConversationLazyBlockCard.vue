<template>
  <div class="chat-lazy-block">
    <div v-if="!loadedBlock" class="chat-data-card chat-lazy-block__summary">
      <div class="chat-card-title">{{ summaryTitle }}</div>
      <div class="chat-card-subtitle">{{ block.block_summary }}</div>
      <div v-if="loadState === 'loading'" class="chat-lazy-block__loading">
        <a-skeleton active :paragraph="{ rows: 2 }" />
      </div>
      <a-alert
        v-else-if="loadState === 'failed'"
        type="error"
        show-icon
        :message="errorMessage || '详情加载失败'"
        class="chat-lazy-block__error"
      />
      <div class="chat-lazy-block__actions">
        <a-button
          v-if="loadState !== 'loading'"
          type="primary"
          size="small"
          ghost
          @click="loadDetail"
        >
          {{ loadState === 'failed' ? '重试' : '展开详情' }}
        </a-button>
      </div>
    </div>

    <ConversationMessageBlockRenderer
      v-else
      :block="loadedBlock"
      :role="role"
      :expand-all-tools="expandAllTools"
      @view-debug="emit('view-debug', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { ConversationBlock } from '../../api/modules/conversations';
import { fetchConversationBlockDetail } from '../../api/modules/conversations';
import ConversationMessageBlockRenderer from './ConversationMessageBlockRenderer.vue';

const props = defineProps<{
  block: ConversationBlock;
  userId: number;
  threadId: string;
  role: 'user' | 'assistant' | 'system';
  expandAllTools?: boolean;
}>();

const emit = defineEmits<{ 'view-debug': [block: ConversationBlock | Record<string, unknown>] }>();

const loadedBlock = ref<ConversationBlock | null>(null);
const loadState = ref<'idle' | 'loading' | 'failed'>('idle');
const errorMessage = ref('');
const loadingRequestId = ref(0);

const summaryTitle = computed(() => {
  const kind = props.block.resolved_kind || props.block.kind;
  const map: Record<string, string> = {
    healthCards: '健康数据',
    structuredHealthCards: '结构化健康数据',
    sleepVisualization: '睡眠数据',
    workoutVisualization: '运动数据',
    nutritionCards: '营养卡片',
    healthResourceReference: '健康资料引用',
    knowledgeCards: '知识卡片',
    tool: '工具调用',
    imageGallery: '图片',
    fileAttachments: '文件附件',
  };
  return map[kind] || '消息卡片';
});

async function loadDetail() {
  if (loadState.value === 'loading') return;
  const requestId = loadingRequestId.value + 1;
  loadingRequestId.value = requestId;
  loadState.value = 'loading';
  errorMessage.value = '';
  try {
    const detail = await fetchConversationBlockDetail(props.userId, props.threadId, props.block.id);
    if (requestId !== loadingRequestId.value) return;
    loadedBlock.value = detail;
    loadState.value = 'idle';
  } catch (error) {
    if (requestId !== loadingRequestId.value) return;
    loadState.value = 'failed';
    errorMessage.value = (error as Error).message || '详情加载失败';
  }
}

watch(
  () => props.block.id,
  () => {
    loadedBlock.value = null;
    loadState.value = 'idle';
    errorMessage.value = '';
    loadingRequestId.value += 1;
  },
);
</script>

<style scoped>
.chat-lazy-block__summary {
  margin-bottom: 8px;
}
.chat-lazy-block__loading {
  margin-top: 8px;
}
.chat-lazy-block__error {
  margin-top: 8px;
}
.chat-lazy-block__actions {
  margin-top: 10px;
}
</style>
