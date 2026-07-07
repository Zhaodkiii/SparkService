<script setup lang="ts">
import type { ShareTimelineEvent } from '../types';
import { formatDay, kindClass, kindLabel } from '../utils';
import ShareAttachmentList from './ShareAttachmentList.vue';

defineProps<{
  event: ShareTimelineEvent;
}>();

const emit = defineEmits<{
  open: [event: ShareTimelineEvent];
}>();

function handleOpen(event: ShareTimelineEvent) {
  if (event.kind === 'meta') return;
  emit('open', event);
}
</script>

<template>
  <article
    class="timeline-row timeline-row-clickable"
    role="button"
    tabindex="0"
    @click="handleOpen(event)"
    @keydown.enter.prevent="handleOpen(event)"
    @keydown.space.prevent="handleOpen(event)"
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

      <ShareAttachmentList
        v-if="event.attachments?.length"
        :attachments="event.attachments"
        inline
      />
    </div>
  </article>
</template>
