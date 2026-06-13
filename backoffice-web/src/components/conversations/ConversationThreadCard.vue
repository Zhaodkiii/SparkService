<template>
  <div :class="['thread-card', { 'thread-card--selected': selected, 'thread-card--deleted': thread.is_deleted }]" @click="emit('select', thread.thread_id)">
    <div class="thread-card-title">
      <span class="title-text">{{ thread.title }}</span>
      <a-tag v-if="thread.is_deleted" color="default">已删除</a-tag>
      <a-tag v-if="thread.is_pinned" color="blue">置顶</a-tag>
      <a-tag v-if="thread.has_failed_message" color="red">失败</a-tag>
    </div>
    <div class="thread-card-info">
      {{ thread.message_count }} 条消息
      <span v-if="thread.current_model_name">| {{ thread.current_model_name }}</span>
    </div>
    <div class="thread-card-date">{{ formatDateTime(thread.last_message_at || thread.updated_at) }}</div>
    <div v-if="thread.message_preview" class="thread-card-preview">{{ thread.message_preview }}</div>
  </div>
</template>

<script setup lang="ts">
import type { ConversationThreadRow } from '../../api/modules/conversations';
import { formatDateTime } from '../../utils/datetime';

defineProps<{
  thread: ConversationThreadRow;
  selected: boolean;
}>();

const emit = defineEmits<{ select: [threadId: string] }>();
</script>

<style scoped>
.thread-card {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.2s, background 0.2s;
}
.thread-card:hover {
  border-color: #d9d9d9;
}
.thread-card--selected {
  border-color: #1677ff;
  background: #f0f7ff;
}
.thread-card--deleted {
  opacity: 0.92;
}
.thread-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.title-text {
  font-weight: 600;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-card-info,
.thread-card-date,
.thread-card-preview {
  color: #666;
  font-size: 12px;
}
.thread-card-preview {
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
