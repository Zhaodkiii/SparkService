<template>
  <div v-if="!isSuperAdmin" class="access-denied">
    <a-result status="403" title="无权限访问" sub-title="对话查看仅面向系统管理员开放。" />
  </div>

  <template v-else>
    <div class="page-header">
      <div>
        <div class="page-title">对话 / 用户对话</div>
        <div class="page-desc">查看系统内有 AI 对话记录的用户，进入后可查看该用户会话与消息详情</div>
      </div>
    </div>

    <a-space wrap style="margin-bottom: 16px">
      <a-input v-model:value="query.user_id" placeholder="用户 ID" style="width: 120px" @pressEnter="load" />
      <a-input-search v-model:value="query.keyword" placeholder="用户名/邮箱" enter-button @search="load" style="width: 260px" />
      <a-range-picker v-model:value="dateRange" show-time format="YYYY-MM-DD HH:mm:ss" @change="onDateChange" />
      <a-input v-model:value="query.model_name" placeholder="模型" allow-clear style="width: 160px" @pressEnter="load" />
      <a-select v-model:value="query.is_active" style="width: 120px" @change="load">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option value="true">启用</a-select-option>
        <a-select-option value="false">禁用</a-select-option>
      </a-select>
      <a-button type="primary" @click="load">查询</a-button>
      <a-button @click="reset">重置</a-button>
    </a-space>

    <a-collapse ghost style="margin-bottom: 12px">
      <a-collapse-panel key="advanced" header="高级筛选">
        <a-space wrap>
          <a-input v-model:value="query.min_message_count" placeholder="最小消息数" style="width: 120px" />
          <a-input v-model:value="query.max_message_count" placeholder="最大消息数" style="width: 120px" />
          <a-input v-model:value="query.min_thread_count" placeholder="最小会话数" style="width: 120px" />
          <a-input v-model:value="query.max_thread_count" placeholder="最大会话数" style="width: 120px" />
          <a-select v-model:value="query.has_user_message" style="width: 160px" allow-clear placeholder="是否有用户消息" @change="load">
            <a-select-option value="true">有用户消息</a-select-option>
            <a-select-option value="false">无用户消息</a-select-option>
          </a-select>
          <a-select v-model:value="query.ordering" style="width: 180px" @change="load">
            <a-select-option value="-last_conversation_at">最近对话时间倒序</a-select-option>
            <a-select-option value="last_conversation_at">最近对话时间正序</a-select-option>
            <a-select-option value="-thread_count">会话数倒序</a-select-option>
            <a-select-option value="-message_count">消息数倒序</a-select-option>
            <a-select-option value="-user_message_count">发送次数倒序</a-select-option>
            <a-select-option value="-date_joined">注册时间倒序</a-select-option>
          </a-select>
        </a-space>
      </a-collapse-panel>
    </a-collapse>

    <div v-if="stats" class="stats-bar">
      有对话用户 {{ stats.user_count }} | 会话 {{ stats.thread_count }} | 用户发送 {{ stats.user_message_count }} | AI 回复
      {{ stats.assistant_message_count }} | 已删除会话 {{ stats.deleted_thread_count }}
    </div>

    <a-table :data-source="rows" row-key="user_id" :pagination="false" :loading="loading" :scroll="{ x: 1500 }">
      <a-table-column title="用户 ID" data-index="user_id" :width="90" />
      <a-table-column title="用户名" data-index="username" :width="160" />
      <a-table-column title="邮箱" data-index="email" :width="220" />
      <a-table-column title="状态" key="status" :width="90">
        <template #default="{ record }">
          <a-tag :color="statusColor(record)">{{ record.user_status }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="会话数" key="thread_count" :width="120">
        <template #default="{ record }">
          {{ record.thread_count }}
          <span v-if="record.deleted_thread_count" class="sub-count">(删 {{ record.deleted_thread_count }})</span>
        </template>
      </a-table-column>
      <a-table-column title="消息总数" key="message_count" :width="120">
        <template #default="{ record }">
          {{ record.message_count }}
          <span v-if="record.tombstone_count" class="sub-count">(删 {{ record.tombstone_count }})</span>
        </template>
      </a-table-column>
      <a-table-column title="发送次数" data-index="user_message_count" :width="100" />
      <a-table-column title="AI 回复" data-index="assistant_message_count" :width="90" />
      <a-table-column title="最近对话时间" key="last_conversation_at" :width="180">
        <template #default="{ record }">{{ formatDateTime(record.last_conversation_at) }}</template>
      </a-table-column>
      <a-table-column title="最近模型" data-index="last_model_name" :width="140" />
      <a-table-column title="最近会话" data-index="last_thread_title" :ellipsis="true" />
      <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" type="primary" @click="openThreads(record.user_id)">查看会话</a-button>
            <a-button size="small" @click="openUserDetail(record.user_id)">用户详情</a-button>
          </TableHoverActions>
        </template>
      </a-table-column>
    </a-table>

    <a-pagination
      style="margin-top: 16px; text-align: right"
      :current="query.page"
      :page-size="query.page_size"
      :total="pagination.total"
      @change="onPageChange"
    />
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import TableHoverActions from '../components/TableHoverActions.vue';
import {
  fetchConversationUsers,
  type ConversationUserRow,
  type ConversationUserStats,
} from '../api/modules/conversations';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import { formatDateTime } from '../utils/datetime';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const router = useRouter();
const auth = useAuthStore();
const isSuperAdmin = computed(() => !!auth.user?.is_superuser);
const actionsColWidth = calcActionsColWidth({ buttons: 2 });

const query = reactive({
  page: 1,
  page_size: 20,
  user_id: '',
  keyword: '',
  started_at: '',
  ended_at: '',
  model_name: '',
  is_active: '',
  has_user_message: '',
  min_message_count: '',
  max_message_count: '',
  min_thread_count: '',
  max_thread_count: '',
  ordering: '-last_conversation_at',
});

const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const rows = ref<ConversationUserRow[]>([]);
const stats = ref<ConversationUserStats | null>(null);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const loading = ref(false);

function statusColor(record: ConversationUserRow) {
  if (record.is_anonymized) return 'default';
  return record.is_active ? 'green' : 'red';
}

function onDateChange(values: [Dayjs, Dayjs] | [string, string] | null) {
  if (!values || !Array.isArray(values) || values.length !== 2) {
    query.started_at = '';
    query.ended_at = '';
  } else {
    query.started_at = dayjs(values[0]).toISOString();
    query.ended_at = dayjs(values[1]).toISOString();
  }
  load();
}

async function load() {
  if (!isSuperAdmin.value) return;
  loading.value = true;
  try {
    const data = await fetchConversationUsers({ ...query });
    rows.value = data.items;
    stats.value = data.stats;
    Object.assign(pagination, data.pagination);
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function reset() {
  query.page = 1;
  query.user_id = '';
  query.keyword = '';
  query.started_at = '';
  query.ended_at = '';
  query.model_name = '';
  query.is_active = '';
  query.has_user_message = '';
  query.min_message_count = '';
  query.max_message_count = '';
  query.min_thread_count = '';
  query.max_thread_count = '';
  query.ordering = '-last_conversation_at';
  dateRange.value = null;
  load();
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

function openThreads(userId: number) {
  router.push(`/conversations/users/${userId}`);
}

function openUserDetail(userId: number) {
  router.push({ path: '/users', query: { openUserId: String(userId) } });
}

onMounted(load);
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.page-desc {
  color: #666;
  margin-top: 4px;
}
.stats-bar {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 8px;
  color: #666;
}
.sub-count {
  color: #999;
  font-size: 12px;
}
.access-denied {
  padding: 48px 0;
}
</style>
