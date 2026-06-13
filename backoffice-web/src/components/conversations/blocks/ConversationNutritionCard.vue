<template>
  <div class="chat-data-card">
    <div class="chat-card-title">
      <CoffeeOutlined style="margin-right: 6px; color: #fa8c16" />
      {{ title }}
    </div>
    <div v-if="subtitle" class="chat-card-subtitle">{{ subtitle }}</div>
    <div v-if="nutrients.length" class="chat-grid-2">
      <div v-for="item in nutrients" :key="item.label" class="chat-grid-item">
        <div class="chat-grid-item__label">{{ item.label }}</div>
        <div class="chat-grid-item__value">{{ item.value }}</div>
      </div>
    </div>
    <div v-if="hint" class="chat-card-subtitle" style="margin-top: 8px">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { CoffeeOutlined } from '@ant-design/icons-vue';
import { nutrientItems, pickCardTitle } from '../../../utils/conversationBlockHelpers';

const props = defineProps<{ card: Record<string, unknown> }>();

const title = computed(() => pickCardTitle(props.card, '营养分析'));
const subtitle = computed(() => String(props.card.date || props.card.recordedAt || props.card.recorded_at || ''));
const nutrients = computed(() => nutrientItems(props.card));
const hint = computed(() => String(props.card.hint || props.card.note || 'AI 估算营养数据'));
</script>
