<template>
  <div :class="['chat-row', `chat-row--${message.role}`, { 'search-hit': highlighted }]">
    <div class="chat-row__inner">
      <div :class="['chat-bubble-shell', `chat-bubble-shell--${message.role}`, { 'chat-bubble-shell--tombstone': message.tombstone }]">
        <div class="chat-bubble-meta">
          <div class="chat-bubble-meta__left">
            <span class="chat-bubble-meta__role">{{ roleLabel(message.role) }}</span>
            <span class="chat-bubble-meta__time">{{ formatDateTime(message.created_at) }}</span>
            <a-tag v-if="stateLabel" size="small" :color="message.delivery_state === 'failed' ? 'red' : 'processing'">
              {{ stateLabel }}
            </a-tag>
            <a-tag v-if="message.tombstone" size="small" color="orange">已删除</a-tag>
            <span v-if="message.role === 'assistant' && message.model_name" class="chat-bubble-meta__model">
              {{ message.model_name }}
            </span>
          </div>
          <a-button type="link" size="small" class="chat-debug-link" @click="emit('view-debug', message)">查看调试数据</a-button>
        </div>

        <div class="chat-bubble-content">
          <template v-for="block in visibleBlocks" :key="block.id">
            <ConversationLazyBlockCard
              v-if="blockNeedsLazyDetail(block)"
              :block="block"
              :user-id="userId"
              :thread-id="threadId"
              :role="message.role"
              :expand-all-tools="expandAllTools"
              @view-debug="emit('view-block-debug', $event)"
            />
            <ConversationMessageBlockRenderer
              v-else
              :block="block"
              :role="message.role"
              :expand-all-tools="expandAllTools"
              @view-debug="emit('view-block-debug', $event)"
            />
          </template>
          <a-empty v-if="visibleBlocks.length === 0" description="暂无可见内容" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Empty } from 'ant-design-vue';
import type { ConversationBlock, ConversationMessage } from '../../api/modules/conversations';
import {
  blockHasVisibleContent,
  blockNeedsLazyDetail,
  deliveryStateLabel,
  roleLabel,
} from '../../utils/conversationBlockHelpers';
import { formatDateTime } from '../../utils/datetime';
import ConversationLazyBlockCard from './ConversationLazyBlockCard.vue';
import ConversationMessageBlockRenderer from './ConversationMessageBlockRenderer.vue';

const props = defineProps<{
  message: ConversationMessage;
  userId: number;
  threadId: string;
  expandAllTools?: boolean;
  highlighted?: boolean;
}>();

const emit = defineEmits<{
  'view-debug': [message: ConversationMessage];
  'view-block-debug': [block: ConversationBlock | Record<string, unknown>];
}>();

const stateLabel = computed(() => deliveryStateLabel(props.message.delivery_state));
const visibleBlocks = computed(() => props.message.blocks.filter((block) => blockHasVisibleContent(block)));
</script>

<style scoped>
.search-hit .chat-bubble-shell {
  box-shadow: 0 0 0 2px #1677ff55;
}
</style>
