<template>
  <div class="chat-timeline">
    <div v-if="loading && messages.length === 0" class="timeline-loading">
      <a-spin tip="加载消息中..." />
    </div>
    <a-empty v-else-if="!loading && messages.length === 0" description="该会话暂无消息" />
    <template v-else>
      <ConversationMessageBubble
        v-for="message in visibleMessages"
        :key="`${message.message_db_id}-${message.client_message_id}`"
        :ref="(el) => setMessageRef(message.message_db_id, el)"
        :message="message"
        :user-id="userId"
        :thread-id="threadId"
        :expand-all-tools="expandAllTools"
        :highlighted="isHit(message.message_db_id)"
        @view-debug="emit('view-message-debug', $event)"
        @view-block-debug="emit('view-block-debug', $event)"
      />
    </template>
    <div v-if="pagination.total > 0" class="timeline-footer">
      已加载 {{ messages.length }} / {{ pagination.total }} 条消息
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type ComponentPublicInstance } from 'vue';
import type { ConversationBlock, ConversationMessage } from '../../api/modules/conversations';
import type { Pagination } from '../../types';
import ConversationMessageBubble from './ConversationMessageBubble.vue';

const props = defineProps<{
  messages: ConversationMessage[];
  pagination: Pagination;
  loading: boolean;
  userId: number;
  threadId: string;
  roleFilter: string;
  includeTombstone: boolean;
  searchKeyword: string;
  searchHitIds: number[];
  currentHitIndex: number;
  expandAllTools?: boolean;
}>();

const emit = defineEmits<{
  'view-message-debug': [message: ConversationMessage];
  'view-block-debug': [block: ConversationBlock | Record<string, unknown>];
}>();

const messageRefs = new Map<number, HTMLElement>();

function setMessageRef(id: number, el: Element | ComponentPublicInstance | null) {
  if (!el) {
    messageRefs.delete(id);
    return;
  }
  const element = el instanceof HTMLElement ? el : ((el as ComponentPublicInstance).$el as HTMLElement);
  if (element) {
    messageRefs.set(id, element);
  }
}

defineExpose({
  scrollToMessage(id: number) {
    messageRefs.get(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  },
});

const visibleMessages = computed(() => {
  let rows = props.messages;
  if (props.roleFilter) {
    rows = rows.filter((item) => item.role === props.roleFilter);
  }
  if (!props.includeTombstone) {
    rows = rows.filter((item) => !item.tombstone);
  }
  return rows;
});

function isHit(messageId: number) {
  if (!props.searchKeyword.trim()) return false;
  return props.searchHitIds[props.currentHitIndex] === messageId;
}
</script>

<style scoped>
.timeline-loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.timeline-footer {
  color: #999;
  font-size: 12px;
  padding: 8px 0 16px;
}
</style>

<style src="../../styles/conversation-chat.css"></style>
