<template>
  <div class="chat-block">
    <template v-if="displayKind === 'text' || displayKind === 'translatedText'">
      <div v-if="textContent" class="chat-markdown" v-html="markdownHtml(textContent)" />
    </template>

    <template v-else-if="displayKind === 'deepThought'">
      <div class="chat-thought-card">
        <a-collapse ghost :active-key="thoughtExpandedKeys">
          <a-collapse-panel key="thought" :header="thoughtHeader">
            <div class="chat-markdown" v-html="markdownHtml(thought.text)" />
          </a-collapse-panel>
        </a-collapse>
      </div>
    </template>

    <template v-else-if="displayKind === 'tool'">
      <ConversationToolBlock
        :block="block"
        :expanded="expandAllTools"
        @view-debug="emit('view-debug', $event)"
      />
    </template>

    <template v-else-if="displayKind === 'imageGallery'">
      <ConversationImageGallery :payload="displayPayload" />
    </template>

    <template v-else-if="displayKind === 'fileAttachments'">
      <div v-for="file in attachments" :key="file.id" class="chat-file-card">
        <div class="chat-file-row">
          <div class="chat-file-icon"><FileOutlined /></div>
          <div class="chat-file-info">
            <div class="chat-file-name">{{ file.name }}</div>
            <div class="chat-file-meta">
              <span v-if="file.mime">{{ file.mime }}</span>
              <span v-if="file.size"> · {{ file.size }}</span>
              <span v-if="!file.url"> · 附件不可访问</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="displayKind === 'nutritionCards'">
      <ConversationNutritionCard v-for="(card, index) in cards" :key="index" :card="card" />
    </template>

    <template v-else-if="isHealthKind">
      <ConversationHealthDataCard
        v-for="(card, index) in cards"
        :key="index"
        :card="card"
        :fallback-title="healthTitle"
      />
    </template>

    <template v-else-if="displayKind === 'medicalRiskNotice' || displayKind === 'medicalDisclaimerCard'">
      <ConversationMedicalNoticeCard :payload="displayPayload" />
    </template>

    <template v-else-if="displayKind === 'healthResourceReference'">
      <div class="chat-data-card">
        <div class="chat-card-title">健康资料引用</div>
        <div class="chat-card-subtitle">{{ resourceSummary }}</div>
      </div>
    </template>

    <template v-else-if="displayKind === 'knowledgeCards'">
      <div class="chat-knowledge-list">
        <div v-for="(card, index) in cards" :key="index" class="chat-knowledge-item">
          <div class="chat-knowledge-item__title">{{ pickCardTitle(card, `知识卡片 ${index + 1}`) }}</div>
          <div v-if="cardSummary(card)" class="chat-knowledge-item__summary">{{ cardSummary(card) }}</div>
        </div>
      </div>
    </template>

    <template v-else-if="displayKind === 'error' || displayKind === 'assistantStatusCard'">
      <a-alert type="error" show-icon :message="textContent || '消息发送失败'" />
    </template>

    <template v-else-if="displayKind === 'html'">
      <pre class="chat-html-source">{{ htmlContent }}</pre>
    </template>

    <template v-else-if="isKnownKind">
      <ConversationHealthDataCard :card="displayPayload" :fallback-title="healthTitle" />
    </template>

    <template v-else>
      <div class="chat-unsupported-card">暂不支持的消息内容</div>
    </template>

    <a-button
      v-if="showDebugAction"
      type="link"
      size="small"
      class="chat-debug-link"
      @click="emit('view-debug', block)"
    >
      调试
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { FileOutlined } from '@ant-design/icons-vue';
import type { ConversationBlock } from '../../api/modules/conversations';
import {
  blockDebugData,
  formatDurationMs,
  pickCardTitle,
  readAttachments,
  readCards,
  readPayloadText,
  readReasoning,
  resolveBlockPresentation,
} from '../../utils/conversationBlockHelpers';
import { renderConversationMarkdown } from '../../utils/conversationRender';
import ConversationHealthDataCard from './blocks/ConversationHealthDataCard.vue';
import ConversationMedicalNoticeCard from './blocks/ConversationMedicalNoticeCard.vue';
import ConversationNutritionCard from './blocks/ConversationNutritionCard.vue';
import ConversationImageGallery from './ConversationImageGallery.vue';
import ConversationToolBlock from './ConversationToolBlock.vue';

const props = withDefaults(
  defineProps<{
    block: ConversationBlock;
    role: 'user' | 'assistant' | 'system';
    expandAllTools?: boolean;
    showDebugAction?: boolean;
  }>(),
  {
    expandAllTools: false,
    showDebugAction: false,
  },
);

const emit = defineEmits<{ 'view-debug': [block: ConversationBlock | Record<string, unknown>] }>();

const healthKinds = new Set([
  'healthCards',
  'structuredHealthCards',
  'sleepVisualization',
  'workoutVisualization',
]);

const knownKinds = new Set([
  'mapRoute',
  'events',
  'pendingMemberToolCards',
  'captureCard',
  'smallTaskCard',
  'taskCards',
]);

const presentation = computed(() => resolveBlockPresentation(props.block));
const displayKind = computed(() => presentation.value.kind);
const displayPayload = computed(() => presentation.value.payload);

const thoughtExpandedKeys = computed(() => (props.expandAllTools ? ['thought'] : []));
const textContent = computed(() => readPayloadText(displayPayload.value));
const htmlContent = computed(() => readPayloadText(displayPayload.value) || String(displayPayload.value?.html || ''));
const thought = computed(() => readReasoning(displayPayload.value));
const thoughtHeader = computed(() => {
  const duration = formatDurationMs(thought.value.durationMs);
  return duration ? `思考过程 · ${duration}` : '思考过程';
});
const attachments = computed(() => readAttachments(displayPayload.value));
const cards = computed(() => readCards(displayPayload.value));
const isHealthKind = computed(() => healthKinds.has(displayKind.value));
const isKnownKind = computed(() => knownKinds.has(displayKind.value));

const healthTitle = computed(() => {
  const map: Record<string, string> = {
    healthCards: '健康数据',
    structuredHealthCards: '结构化健康数据',
    sleepVisualization: '睡眠数据',
    workoutVisualization: '运动数据',
    mapRoute: '地图路线',
    events: '日程事件',
    pendingMemberToolCards: '待选成员',
    captureCard: '采集卡片',
    smallTaskCard: '小任务',
    taskCards: '任务提醒',
  };
  return map[displayKind.value] || '消息卡片';
});

function markdownHtml(text: string) {
  return renderConversationMarkdown(text);
}

function cardSummary(card: Record<string, unknown>) {
  for (const key of ['summary', 'description', 'content', 'text']) {
    const value = card[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '';
}

const resourceSummary = computed(() => {
  const payload = displayPayload.value;
  for (const key of ['title', 'resourceTitle', 'resource_title', 'summary', 'name']) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return '已引用健康资料';
});

defineExpose({ blockDebugData: () => blockDebugData(props.block) });
</script>
