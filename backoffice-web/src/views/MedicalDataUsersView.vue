<template>
  <div class="page-header">
    <div>
      <div class="page-title">医疗数据 / 用户医疗数据</div>
      <div class="page-desc">轻量列表 + 预聚合统计，成员与分类明细按需分页加载</div>
    </div>
  </div>

  <a-row :gutter="16" style="margin-bottom: 16px">
    <a-col v-for="card in statCards" :key="card.key" :span="6">
      <a-card size="small">
        <a-skeleton v-if="statsLoading" active :paragraph="{ rows: 1 }" />
        <template v-else>
          <a-statistic :title="card.title" :value="card.value" />
          <a-tag v-if="stats?.stats_status === 'stale'" color="orange" style="margin-top: 4px">统计刷新中</a-tag>
        </template>
      </a-card>
    </a-col>
  </a-row>

  <a-space wrap style="margin-bottom: 16px">
    <a-input v-model:value="query.user_id" placeholder="用户 ID" style="width: 120px" @pressEnter="load" />
    <a-input-search
      v-model:value="query.keyword"
      placeholder="用户名/邮箱"
      enter-button
      @search="load"
      style="width: 260px"
    />
    <a-select v-model:value="query.data_type" style="width: 140px" @change="load">
      <a-select-option v-for="opt in DATA_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</a-select-option>
    </a-select>
    <a-range-picker v-model:value="dateRange" show-time format="YYYY-MM-DD HH:mm:ss" @change="onDateChange" />
    <a-select v-model:value="query.has_attachment" style="width: 130px" allow-clear placeholder="附件" @change="load">
      <a-select-option value="true">有附件</a-select-option>
      <a-select-option value="false">无附件</a-select-option>
    </a-select>
    <a-select v-model:value="query.has_ai_task" style="width: 150px" allow-clear placeholder="AI 识别" @change="load">
      <a-select-option value="true">有 AI 识别</a-select-option>
      <a-select-option value="false">无 AI 识别</a-select-option>
    </a-select>
    <a-select v-model:value="query.status" style="width: 120px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="active">启用</a-select-option>
      <a-select-option value="inactive">禁用</a-select-option>
      <a-select-option value="deactivated">已注销</a-select-option>
    </a-select>
    <a-select v-model:value="query.ordering" style="width: 180px" @change="load">
      <a-select-option value="-last_updated">最近更新倒序</a-select-option>
      <a-select-option value="last_updated">最近更新正序</a-select-option>
      <a-select-option value="-medical_data_total">数据量倒序</a-select-option>
    </a-select>
    <a-button type="primary" @click="load">查询</a-button>
    <a-button @click="reset">重置</a-button>
  </a-space>

  <a-alert
    v-if="loadError"
    type="error"
    show-icon
    style="margin-bottom: 12px"
    :message="loadError"
    closable
  >
    <template #action>
      <a-button size="small" @click="load">重试</a-button>
    </template>
  </a-alert>

  <a-table
    :data-source="rows"
    row-key="user_id"
    :pagination="false"
    :loading="loading"
    :scroll="{ x: 1600 }"
  >
    <template #emptyText>
      <a-empty :description="emptyDescription" />
    </template>
    <a-table-column title="用户 ID" data-index="user_id" :width="90" />
    <a-table-column title="用户名" data-index="username" :width="140" />
    <a-table-column title="邮箱" data-index="email" :width="200" />
    <a-table-column title="状态" key="status" :width="90">
      <template #default="{ record }">
        <a-tag :color="statusColor(record)">{{ record.user_status }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="成员数" data-index="member_count" :width="80" />
    <a-table-column title="有数据成员" data-index="members_with_data_count" :width="100" />
    <a-table-column title="数据总数" data-index="medical_data_total" :width="90" />
    <a-table-column title="附件数" data-index="attachment_count" :width="80" />
    <a-table-column title="AI 任务" data-index="ai_task_count" :width="80" />
    <a-table-column title="最近更新" key="last_updated_at" :width="170">
      <template #default="{ record }">{{ formatDateTime(record.last_updated_at) }}</template>
    </a-table-column>
    <a-table-column title="最近来源" data-index="last_source" :width="100" />
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" type="primary" @click="openMembers(record.user_id)">查看成员</a-button>
          <a-button size="small" @click="openConversations(record.user_id)">查看对话</a-button>
          <a-button size="small" @click="openTasks">查看任务</a-button>
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

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';
import TableHoverActions from '../components/TableHoverActions.vue';
import {
  DATA_TYPE_OPTIONS,
  fetchMedicalDataGlobalStats,
  fetchMedicalDataUsers,
  type MedicalDataGlobalStats,
  type MedicalDataUserRow,
} from '../api/modules/medicalData';
import type { Pagination } from '../types';
import { formatDateTime } from '../utils/datetime';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { useDebouncedFn } from '../utils/useDebouncedFn';

const router = useRouter();
const actionsColWidth = calcActionsColWidth({ buttons: 3 });

const query = reactive({
  page: 1,
  page_size: 20,
  user_id: '',
  keyword: '',
  data_type: '',
  has_attachment: '',
  has_ai_task: '',
  status: '',
  updated_after: '',
  updated_before: '',
  ordering: '-last_updated',
});

const dateRange = ref<[Dayjs, Dayjs] | null>(null);
const rows = ref<MedicalDataUserRow[]>([]);
const stats = ref<MedicalDataGlobalStats | null>(null);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const loading = ref(false);
const statsLoading = ref(false);
const loadError = ref('');
const hasFilters = computed(
  () =>
    !!query.user_id ||
    !!query.keyword ||
    !!query.data_type ||
    !!query.has_attachment ||
    !!query.has_ai_task ||
    !!query.status ||
    !!query.updated_after,
);
const emptyDescription = computed(() => (hasFilters.value ? '筛选无结果' : '暂无医疗数据用户'));

let listAbort: AbortController | null = null;

const statCards = computed(() => [
  { key: 'users', title: '有医疗数据用户', value: stats.value?.users_with_medical_data ?? 0 },
  { key: 'ai', title: '有 AI 识别用户', value: stats.value?.users_with_ai_recognition ?? 0 },
  { key: 'total', title: '医疗数据总量', value: stats.value?.medical_data_total ?? 0 },
  { key: 'attach', title: '附件总量', value: stats.value?.attachment_total ?? 0 },
]);

function statusColor(record: MedicalDataUserRow) {
  if (record.is_anonymized) return 'default';
  return record.is_active ? 'green' : 'red';
}

function onDateChange(dates: [Dayjs, Dayjs] | null) {
  query.updated_after = dates?.[0]?.format('YYYY-MM-DD HH:mm:ss') || '';
  query.updated_before = dates?.[1]?.format('YYYY-MM-DD HH:mm:ss') || '';
}

async function loadStats() {
  statsLoading.value = true;
  try {
    const data = await fetchMedicalDataGlobalStats();
    stats.value = data.stats;
  } catch {
    stats.value = null;
  } finally {
    statsLoading.value = false;
  }
}

async function load() {
  loadError.value = '';
  loading.value = true;
  listAbort?.abort();
  listAbort = new AbortController();
  try {
    const data = await fetchMedicalDataUsers({ ...query }, { signal: listAbort.signal });
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } catch (err) {
    if ((err as Error).name === 'CanceledError' || (err as Error).message?.includes('canceled')) {
      return;
    }
    loadError.value = (err as Error).message || '加载失败';
    message.error(loadError.value);
  } finally {
    loading.value = false;
  }
}

const debouncedKeywordLoad = useDebouncedFn(() => {
  query.page = 1;
  load();
}, 400);

watch(
  () => query.keyword,
  () => debouncedKeywordLoad(),
);

function reset() {
  query.page = 1;
  query.user_id = '';
  query.keyword = '';
  query.data_type = '';
  query.has_attachment = '';
  query.has_ai_task = '';
  query.status = '';
  query.updated_after = '';
  query.updated_before = '';
  query.ordering = '-last_updated';
  dateRange.value = null;
  load();
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

function openMembers(userId: number) {
  router.push(`/medical-data/users/${userId}`);
}

function openConversations(userId: number) {
  router.push(`/conversations/users/${userId}`);
}

function openTasks() {
  router.push('/tasks');
}

onMounted(async () => {
  await Promise.all([loadStats(), load()]);
});

onUnmounted(() => listAbort?.abort());
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
  color: rgba(0, 0, 0, 0.45);
  margin-top: 4px;
}
</style>
