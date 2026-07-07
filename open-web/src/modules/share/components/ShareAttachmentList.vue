<script setup lang="ts">
import type { ShareAttachment } from '../types';
import { attachmentDisplayName, openAttachment } from '../utils';

defineProps<{
  attachments: ShareAttachment[];
  inline?: boolean;
}>();
</script>

<template>
  <div v-if="attachments.length" class="attachment-strip" :class="{ 'timeline-attachments': inline }">
    <a
      v-for="(attachment, index) in attachments"
      :key="attachment.id"
      class="attachment-pill"
      :class="{ 'attachment-pill-inline': inline }"
      href="#"
      @click.prevent="openAttachment(attachment)"
    >
      <span class="attachment-icon">⤓</span>
      <span class="attachment-name">{{ attachmentDisplayName(index) }}</span>
    </a>
  </div>
</template>
