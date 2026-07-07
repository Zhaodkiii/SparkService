<script setup lang="ts">
import type { ShareTimelineEvent } from '../types';
import ShareTimelineItem from './ShareTimelineItem.vue';

defineProps<{
  timeline: ShareTimelineEvent[];
}>();

const emit = defineEmits<{
  openEvent: [event: ShareTimelineEvent];
}>();
</script>

<template>
  <section class="timeline-section">
    <div class="section-head">
      <h3>时间线</h3>
      <p>{{ timeline.length }} 条记录</p>
    </div>

    <div v-if="timeline.length === 0" class="empty-timeline">
      暂无公开时间线内容
    </div>

    <ShareTimelineItem
      v-for="event in timeline"
      :key="event.id"
      :event="event"
      @open="emit('openEvent', $event)"
    />
  </section>
</template>
