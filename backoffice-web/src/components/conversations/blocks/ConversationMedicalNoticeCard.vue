<template>
  <div class="chat-notice-card" :class="`chat-notice-card--${notice.riskLevel}`">
    <div class="chat-card-title">
      <MedicineBoxOutlined style="margin-right: 6px" />
      {{ notice.title }}
      <a-tag :color="riskColor" style="margin-left: 8px">{{ notice.riskLevel }}</a-tag>
    </div>
    <div v-if="notice.message" style="line-height: 1.6">{{ notice.message }}</div>
    <div v-if="notice.recommendedAction" class="chat-card-subtitle" style="margin-top: 8px">
      建议：{{ notice.recommendedAction }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { MedicineBoxOutlined } from '@ant-design/icons-vue';
import { medicalNotice } from '../../../utils/conversationBlockHelpers';

const props = defineProps<{ payload: Record<string, unknown> }>();

const notice = computed(() => medicalNotice(props.payload));
const riskColor = computed(() => {
  const level = notice.value.riskLevel.toLowerCase();
  if (level.includes('high') || level.includes('emergency')) return 'red';
  if (level.includes('medium')) return 'orange';
  return 'default';
});
</script>
