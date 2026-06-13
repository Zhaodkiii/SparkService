<template>
  <div v-if="!isSuperAdmin" class="access-denied">
    <a-result status="403" title="无权限访问" sub-title="对话查看仅面向系统管理员开放。" />
  </div>

  <template v-else>
    <div class="detail-header">
      <a-button type="link" @click="router.push('/conversations/users')">← 返回用户对话</a-button>
      <div v-if="summary" class="summary-row">
        <span>用户：{{ summary.user.username }}</span>
        <span>ID: {{ summary.user.user_id }} <ConversationCopyButton :value="summary.user.user_id" tooltip="复制 user_id" /></span>
        <a-tag :color="summary.user.is_anonymized ? 'default' : summary.user.is_active ? 'green' : 'red'">
          {{ summary.user.user_status }}
        </a-tag>
        <span>会话：{{ summary.stats.thread_count }}</span>
        <span>消息：{{ summary.stats.message_count }}</span>
        <span>用户发送：{{ summary.stats.user_message_count }}</span>
        <span>最近对话：{{ formatDateTime(summary.stats.last_conversation_at) }}</span>
        <a-button size="small" @click="userDetailOpen = true">用户详情</a-button>
      </div>
    </div>

    <div class="detail-layout">
      <aside class="sidebar">
        <ConversationThreadList
          :threads="threads"
          :pagination="threadPagination"
          :loading="threadsLoading"
          :selected-thread-id="selectedThreadId"
          v-model:keyword="threadQuery.keyword"
          v-model:deleted-filter="threadQuery.deleted_filter"
          v-model:model-name="threadQuery.model_name"
          @select="selectThread"
          @search="loadThreads"
          @page-change="onThreadPageChange"
        />
      </aside>

      <main class="main-panel">
        <a-empty v-if="!selectedThreadId" description="请选择左侧会话查看消息详情" />
        <template v-else>
          <div v-if="threadInfo" class="thread-info">
            <div class="thread-info-title">
              <span>会话标题：{{ threadInfo.title }}</span>
              <a-tag v-if="threadInfo.is_deleted">已删除</a-tag>
            </div>
            <div class="thread-info-meta">
              <span>Thread ID: {{ threadInfo.thread_id }} <ConversationCopyButton :value="threadInfo.thread_id" tooltip="复制 thread_id" /></span>
              <span>场景: {{ threadInfo.scenario }}</span>
              <span>模型: {{ threadInfo.current_model_name || '-' }}</span>
              <span>创建: {{ formatDateTime(threadInfo.created_at) }}</span>
              <span>更新: {{ formatDateTime(threadInfo.updated_at) }}</span>
              <span>删除状态: {{ threadInfo.is_deleted ? formatDateTime(threadInfo.deleted_at) : '正常' }}</span>
            </div>
            <a-collapse v-if="threadInfo.role_prompt" ghost>
              <a-collapse-panel key="role_prompt" header="role_prompt">
                <pre class="json-inline"><code>{{ threadInfo.role_prompt }}</code></pre>
              </a-collapse-panel>
            </a-collapse>
          </div>

          <div class="message-toolbar">
            <a-input-search
              v-model:value="messageSearch"
              placeholder="搜索当前会话消息"
              enter-button
              style="width: 260px"
              @search="runMessageSearch"
            />
            <a-button :disabled="searchHits.length === 0" @click="gotoPrevHit">上一条</a-button>
            <a-button :disabled="searchHits.length === 0" @click="gotoNextHit">下一条</a-button>
            <a-select v-model:value="roleFilter" style="width: 120px" allow-clear placeholder="角色筛选">
              <a-select-option value="user">user</a-select-option>
              <a-select-option value="assistant">assistant</a-select-option>
              <a-select-option value="system">system</a-select-option>
            </a-select>
            <a-switch v-model:checked="includeTombstone" checked-children="含已删除" un-checked-children="隐藏已删除" />
            <a-button @click="expandAllTools = true">展开全部工具</a-button>
            <a-button @click="expandAllTools = false">收起全部工具</a-button>
            <a-button @click="reloadMessages">刷新</a-button>
            <a-button @click="openThreadDebug">查看调试数据</a-button>
          </div>

          <div class="chat-panel">
            <ConversationMessageTimeline
              ref="timelineRef"
              :messages="messages"
              :pagination="messagePagination"
              :loading="messagesLoading"
              :user-id="userId"
              :thread-id="selectedThreadId"
              :role-filter="roleFilter"
              :include-tombstone="includeTombstone"
              :search-keyword="messageSearch"
              :search-hit-ids="searchHits"
              :current-hit-index="currentHitIndex"
              :expand-all-tools="expandAllTools"
              @view-message-debug="openMessageDebug"
              @view-block-debug="openBlockDebug"
            />
          </div>

          <div v-if="loadedMessagePage > 1" class="load-more">
            <a-button :loading="messagesLoading" @click="loadMoreMessages">向上加载历史消息</a-button>
          </div>
        </template>
      </main>
    </div>

    <ConversationDebugViewer
      v-model:open="debugModal.open"
      :title="debugModal.title"
      :data="debugModal.data"
      :loading="debugModal.loading"
      :load-error="debugModal.loadError"
      @retry="retryDebugLoad"
    />
    <MedicalDataUserOverviewModal v-model:open="userDetailOpen" :user-id="userId" />
  </template>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import { updateTabTitleKey } from '../composables/useAdminTabs';
import ConversationCopyButton from '../components/conversations/ConversationCopyButton.vue';
import ConversationDebugViewer from '../components/conversations/ConversationDebugViewer.vue';
import ConversationMessageTimeline from '../components/conversations/ConversationMessageTimeline.vue';
import ConversationThreadList from '../components/conversations/ConversationThreadList.vue';
import MedicalDataUserOverviewModal from '../components/medical/MedicalDataUserOverviewModal.vue';
import {
  fetchConversationBlockDetail,
  fetchConversationMessageDebug,
  fetchConversationMessages,
  fetchConversationThreads,
  fetchConversationUserSummary,
  type ConversationBlock,
  type ConversationMessage,
  type ConversationThreadRow,
  type ConversationUserSummary,
} from '../api/modules/conversations';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import { blockDebugData } from '../utils/conversationBlockHelpers';
import { formatDateTime } from '../utils/datetime';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const updateTabTitle = inject(updateTabTitleKey, null);
const isSuperAdmin = computed(() => !!auth.user?.is_superuser);
const userId = computed(() => Number(route.params.userId));

const summary = ref<ConversationUserSummary | null>(null);
const threads = ref<ConversationThreadRow[]>([]);
const threadPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const threadQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: '',
  deleted_filter: 'all' as 'all' | 'active' | 'deleted',
  model_name: '',
});
const threadsLoading = ref(false);
const selectedThreadId = ref('');
const threadInfo = ref<ConversationThreadRow | null>(null);

const messages = ref<ConversationMessage[]>([]);
const messagePagination = reactive<Pagination>({ page: 1, page_size: 50, total: 0, total_pages: 0 });
const loadedMessagePage = ref(1);
const messagesLoading = ref(false);
const roleFilter = ref('');
const includeTombstone = ref(true);
const messageSearch = ref('');
const searchHits = ref<number[]>([]);
const currentHitIndex = ref(0);
const expandAllTools = ref(false);
const timelineRef = ref<InstanceType<typeof ConversationMessageTimeline> | null>(null);
const userDetailOpen = ref(false);

const debugModal = reactive<{
  open: boolean;
  title: string;
  data: unknown;
  loading: boolean;
  loadError: string;
  retry: (() => Promise<void>) | null;
}>({
  open: false,
  title: '查看调试数据',
  data: null,
  loading: false,
  loadError: '',
  retry: null,
});

let messagesAbort: AbortController | null = null;
let debugAbort: AbortController | null = null;
let activeMessageRequestId = 0;

async function loadSummary() {
  summary.value = await fetchConversationUserSummary(userId.value);
  if (summary.value) {
    updateTabTitle?.(route.fullPath, `${summary.value.user.username} · 会话详情`);
  }
}

async function loadThreads() {
  threadsLoading.value = true;
  try {
    const data = await fetchConversationThreads(userId.value, { ...threadQuery });
    threads.value = data.items;
    Object.assign(threadPagination, data.pagination);
    if (!selectedThreadId.value && data.items.length > 0) {
      selectThread(data.items[0].thread_id);
    }
  } catch (error: any) {
    message.error(error?.message || '加载会话失败');
  } finally {
    threadsLoading.value = false;
  }
}

async function loadMessages(reset = true) {
  if (!selectedThreadId.value) return;
  messagesAbort?.abort();
  messagesAbort = new AbortController();
  const requestId = ++activeMessageRequestId;
  const threadId = selectedThreadId.value;
  const signal = messagesAbort.signal;
  messagesLoading.value = true;
  try {
    const baseParams = {
      page_size: messagePagination.page_size,
      include_tombstone: includeTombstone.value ? 'true' : 'false',
      include_raw: 'false',
    };
    if (reset) {
      const probe = await fetchConversationMessages(userId.value, threadId, { page: 1, ...baseParams }, { signal });
      if (requestId !== activeMessageRequestId || threadId !== selectedThreadId.value) return;
      threadInfo.value = probe.thread;
      Object.assign(messagePagination, probe.pagination);
      const targetPage = probe.pagination.total_pages || 1;
      loadedMessagePage.value = targetPage;
      if (targetPage === 1) {
        messages.value = probe.items;
      } else {
        const data = await fetchConversationMessages(
          userId.value,
          threadId,
          { page: targetPage, ...baseParams },
          { signal },
        );
        if (requestId !== activeMessageRequestId || threadId !== selectedThreadId.value) return;
        messages.value = data.items;
      }
    } else if (loadedMessagePage.value > 1) {
      const previousPage = loadedMessagePage.value - 1;
      const data = await fetchConversationMessages(
        userId.value,
        threadId,
        { page: previousPage, ...baseParams },
        { signal },
      );
      if (requestId !== activeMessageRequestId || threadId !== selectedThreadId.value) return;
      messages.value = [...data.items, ...messages.value];
      loadedMessagePage.value = previousPage;
    }
    runMessageSearch();
  } catch (error: any) {
    if (error?.name === 'CanceledError' || String(error?.message || '').toLowerCase().includes('cancel')) {
      return;
    }
    message.error(error?.message || '加载消息失败');
  } finally {
    if (requestId === activeMessageRequestId) {
      messagesLoading.value = false;
    }
  }
}

function selectThread(threadId: string) {
  if (selectedThreadId.value === threadId) return;
  selectedThreadId.value = threadId;
  messagePagination.page = 1;
  messages.value = [];
  loadMessages(true);
}

function reloadMessages() {
  loadMessages(true);
}

function loadMoreMessages() {
  loadMessages(false);
}

function onThreadPageChange(page: number, pageSize: number) {
  threadQuery.page = page;
  threadQuery.page_size = pageSize;
  loadThreads();
}

function messageMatchesSearch(item: ConversationMessage, keyword: string) {
  const lower = keyword.toLowerCase();
  const haystacks = [
    item.message_preview,
    item.model_name || '',
    item.client_message_id,
    item.server_message_id || '',
    JSON.stringify(item.blocks),
    JSON.stringify(item.metadata),
  ];
  return haystacks.some((part) => String(part).toLowerCase().includes(lower));
}

function runMessageSearch() {
  const keyword = messageSearch.value.trim();
  if (!keyword) {
    searchHits.value = [];
    currentHitIndex.value = 0;
    return;
  }
  searchHits.value = messages.value.filter((item) => messageMatchesSearch(item, keyword)).map((item) => item.message_db_id);
  currentHitIndex.value = 0;
  scrollToCurrentHit();
}

function scrollToCurrentHit() {
  const id = searchHits.value[currentHitIndex.value];
  if (id) {
    timelineRef.value?.scrollToMessage(id);
  }
}

function gotoPrevHit() {
  if (searchHits.value.length === 0) return;
  currentHitIndex.value = (currentHitIndex.value - 1 + searchHits.value.length) % searchHits.value.length;
  scrollToCurrentHit();
}

function gotoNextHit() {
  if (searchHits.value.length === 0) return;
  currentHitIndex.value = (currentHitIndex.value + 1) % searchHits.value.length;
  scrollToCurrentHit();
}

function openMessageDebug(item: ConversationMessage) {
  debugModal.title = `消息调试数据 · ${item.message_db_id}`;
  debugModal.open = true;
  debugModal.retry = () => loadMessageDebug(item);
  loadMessageDebug(item);
}

async function loadMessageDebug(item: ConversationMessage) {
  debugAbort?.abort();
  debugAbort = new AbortController();
  debugModal.loading = true;
  debugModal.loadError = '';
  debugModal.data = null;
  try {
    const data = await fetchConversationMessageDebug(
      userId.value,
      selectedThreadId.value,
      item.message_db_id,
      { signal: debugAbort.signal },
    );
    debugModal.data = {
      ...data,
      blocks: data.blocks.map((block) => blockDebugData(block)),
    };
  } catch (error: any) {
    if (error?.name === 'CanceledError' || String(error?.message || '').toLowerCase().includes('cancel')) {
      return;
    }
    debugModal.loadError = error?.message || '调试数据加载失败';
  } finally {
    debugModal.loading = false;
  }
}

async function retryDebugLoad() {
  if (debugModal.retry) {
    await debugModal.retry();
  }
}

async function openBlockDebug(block: ConversationBlock | Record<string, unknown>) {
  const conversationBlock = block as ConversationBlock;
  if (!('id' in conversationBlock) || !selectedThreadId.value) {
    debugModal.title = 'Block 调试数据';
    debugModal.data = block;
    debugModal.open = true;
    debugModal.loading = false;
    debugModal.loadError = '';
    debugModal.retry = null;
    return;
  }
  debugModal.title = `Block 调试数据 · ${conversationBlock.kind}`;
  debugModal.open = true;
  debugModal.retry = async () => {
    debugModal.loading = true;
    debugModal.loadError = '';
    try {
      const detail = await fetchConversationBlockDetail(
        userId.value,
        selectedThreadId.value,
        conversationBlock.id,
      );
      debugModal.data = blockDebugData(detail);
    } catch (error: any) {
      debugModal.loadError = error?.message || '调试数据加载失败';
    } finally {
      debugModal.loading = false;
    }
  };
  await debugModal.retry();
}

function openThreadDebug() {
  debugModal.title = '会话调试数据';
  debugModal.data = threadInfo.value;
  debugModal.open = true;
  debugModal.loading = false;
  debugModal.loadError = '';
  debugModal.retry = null;
}

watch(includeTombstone, () => loadMessages(true));

onMounted(async () => {
  if (!isSuperAdmin.value) return;
  try {
    await loadSummary();
    await loadThreads();
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  }
});
</script>

<style scoped>
.detail-header {
  margin-bottom: 12px;
}
.summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 8px;
}
.detail-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  min-height: calc(100vh - 220px);
}
.sidebar {
  border-right: 1px solid #f0f0f0;
  padding-right: 12px;
}
.main-panel {
  min-width: 0;
}
.thread-info {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
  background: #fafafa;
}
.thread-info-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}
.thread-info-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #666;
  font-size: 12px;
}
.message-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.chat-panel {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 12px;
  padding: 12px;
  min-height: 420px;
}
.load-more {
  display: flex;
  justify-content: center;
  margin-top: 12px;
}
.json-inline {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  border-radius: 8px;
  padding: 10px;
}
.access-denied {
  padding: 48px 0;
}
@media (max-width: 1024px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    border-right: none;
    border-bottom: 1px solid #f0f0f0;
    padding-right: 0;
    padding-bottom: 12px;
  }
}
</style>
