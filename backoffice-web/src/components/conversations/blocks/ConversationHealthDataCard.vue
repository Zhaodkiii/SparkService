<template>
  <div class="chat-data-card">
    <div class="chat-card-title">{{ title }}</div>
    <div v-if="subtitle" class="chat-card-subtitle">{{ subtitle }}</div>
    <div v-if="lines.length" class="chat-grid-2">
      <div v-for="line in lines" :key="line.label" class="chat-grid-item">
        <div class="chat-grid-item__label">{{ line.label }}</div>
        <div class="chat-grid-item__value">{{ line.value }}</div>
      </div>
    </div>
    <div v-if="extraText" class="chat-card-subtitle" style="margin-top: 8px; white-space: pre-wrap">{{ extraText }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { pickCardLines, pickCardTitle } from '../../../utils/conversationBlockHelpers';

const props = withDefaults(
  defineProps<{
    card: Record<string, unknown>;
    fallbackTitle?: string;
    fieldKeys?: string[];
  }>(),
  {
    fallbackTitle: '健康数据',
    fieldKeys: () => [
      'value',
      'unit',
      'metricName',
      'metric_name',
      'recordedAt',
      'recorded_at',
      'summary',
      'duration',
      'steps',
      'heartRate',
      'heart_rate',
    ],
  },
);

const title = computed(() => pickCardTitle(props.card, props.fallbackTitle));
const subtitle = computed(() => String(props.card.category || props.card.type || props.card.kind || ''));
const lines = computed(() => pickCardLines(props.card, props.fieldKeys));
const extraText = computed(() => String(props.card.description || props.card.detail || props.card.note || ''));
</script>
