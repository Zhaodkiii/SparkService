<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue';
import type { ShareCasePayload, ShareTimelineEvent } from '../types';
import { formatDate, kindClass, kindLabel, kindTitle } from '../utils';
import ShareDetailContent from './ShareDetailContent.vue';

const props = defineProps<{
  visible: boolean;
  event: ShareTimelineEvent | null;
  casePayload: ShareCasePayload | null;
}>();

const emit = defineEmits<{
  close: [];
}>();

watch(
  () => props.visible,
  (visible) => {
    document.body.style.overflow = visible ? 'hidden' : '';
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  document.body.style.overflow = '';
});
</script>

<template>
  <Transition name="fade">
    <section
      v-if="visible && event"
      class="detail-overlay"
      @click.self="emit('close')"
    >
      <article class="detail-sheet" :class="kindClass(event.kind)">
        <header class="detail-sheet-header">
          <div class="detail-heading">
            <p class="eyebrow">{{ kindTitle(event.kind) }}</p>
            <h2>{{ event.title }}</h2>
            <p class="subtle">{{ formatDate(event.date) }}</p>
          </div>
          <button
            class="icon-button"
            type="button"
            aria-label="关闭详情"
            @click="emit('close')"
          >
            ×
          </button>
        </header>

        <div class="detail-hero">
          <span class="detail-kind-chip" :class="kindClass(event.kind)">{{ kindLabel(event.kind) }}</span>
          <span v-if="event.status_badge_text" class="status-chip">{{ event.status_badge_text }}</span>
        </div>

        <div class="detail-scroll">
          <ShareDetailContent
            mode="event"
            :event="event"
            :case-payload="casePayload"
          />
        </div>
      </article>
    </section>
  </Transition>
</template>
