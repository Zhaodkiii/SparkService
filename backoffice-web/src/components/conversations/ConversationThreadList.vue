<template>
  <div class="thread-list">
    <div class="thread-list-toolbar">
      <a-input-search v-model:value="keywordModel" placeholder="搜索会话标题/会话ID" enter-button @search="emitSearch" />
      <a-segmented v-model:value="deletedFilterModel" :options="deletedOptions" @change="emitSearch" />
      <a-input v-model:value="modelNameModel" placeholder="模型筛选" allow-clear @pressEnter="emitSearch" />
    </div>

    <a-spin :spinning="loading">
      <div class="thread-list-body">
        <a-empty v-if="!loading && threads.length === 0" description="暂无会话" />
        <ConversationThreadCard
          v-for="thread in threads"
          :key="thread.thread_id"
          :thread="thread"
          :selected="thread.thread_id === selectedThreadId"
          @select="emit('select', $event)"
        />
      </div>
    </a-spin>

    <div v-if="pagination.total_pages > 1" class="thread-list-footer">
      <a-pagination
        size="small"
        :current="pagination.page"
        :page-size="pagination.page_size"
        :total="pagination.total"
        @change="(page: number, pageSize: number) => emit('page-change', page, pageSize)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ConversationThreadRow } from '../../api/modules/conversations';
import type { Pagination } from '../../types';
import ConversationThreadCard from './ConversationThreadCard.vue';

const props = defineProps<{
  threads: ConversationThreadRow[];
  pagination: Pagination;
  loading: boolean;
  selectedThreadId: string;
  keyword: string;
  deletedFilter: 'all' | 'active' | 'deleted';
  modelName: string;
}>();

const emit = defineEmits<{
  select: [threadId: string];
  search: [];
  'page-change': [page: number, pageSize: number];
  'update:keyword': [value: string];
  'update:deletedFilter': [value: 'all' | 'active' | 'deleted'];
  'update:modelName': [value: string];
}>();

const deletedOptions = [
  { label: '全部', value: 'all' },
  { label: '正常', value: 'active' },
  { label: '已删除', value: 'deleted' },
];

const keywordModel = computed({
  get: () => props.keyword,
  set: (value: string) => emit('update:keyword', value),
});
const deletedFilterModel = computed({
  get: () => props.deletedFilter,
  set: (value: 'all' | 'active' | 'deleted') => emit('update:deletedFilter', value),
});
const modelNameModel = computed({
  get: () => props.modelName,
  set: (value: string) => emit('update:modelName', value),
});

function emitSearch() {
  emit('search');
}
</script>

<style scoped>
.thread-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.thread-list-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.thread-list-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
  max-height: calc(100vh - 320px);
  padding-right: 4px;
}
.thread-list-footer {
  display: flex;
  justify-content: center;
}
</style>
