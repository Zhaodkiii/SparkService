<template>
  <a-card :bordered="false" style="margin-bottom: 16px">
    <a-space wrap>
      <a-select v-model:value="query.window_hours" style="width: 160px" @change="load">
        <a-select-option :value="6">近 6 小时</a-select-option>
        <a-select-option :value="24">近 24 小时</a-select-option>
        <a-select-option :value="72">近 72 小时</a-select-option>
        <a-select-option :value="168">近 7 天</a-select-option>
      </a-select>
      <a-select v-model:value="query.limit" style="width: 140px" @change="load">
        <a-select-option :value="20">最近 20 条</a-select-option>
        <a-select-option :value="50">最近 50 条</a-select-option>
        <a-select-option :value="100">最近 100 条</a-select-option>
      </a-select>
      <a-switch v-model:checked="autoRefresh" checked-children="自动刷新" un-checked-children="手动刷新" />
      <a-button :loading="loading" @click="load">刷新</a-button>
      <span style="color: #999">上次刷新：{{ lastUpdatedText }}</span>
    </a-space>
  </a-card>

  <a-row :gutter="16">
    <a-col :xs="24" :md="12" :xl="6"><a-card title="任务总数">{{ data?.summary.total_recent ?? '-' }}</a-card></a-col>
    <a-col :xs="24" :md="12" :xl="6"><a-card title="失败率">{{ data ? `${data.summary.failure_rate}%` : '-' }}</a-card></a-col>
    <a-col :xs="24" :md="12" :xl="6"><a-card title="运行中（含重试）">{{ data?.summary.running_like ?? '-' }}</a-card></a-col>
    <a-col :xs="24" :md="12" :xl="6"><a-card title="周期任务（启用/总数）">{{ data ? `${data.summary.periodic_enabled}/${data.summary.periodic_total}` : '-' }}</a-card></a-col>
  </a-row>

  <a-row :gutter="16" style="margin-top: 16px">
    <a-col :xs="24" :md="12">
      <a-card title="通知任务">
        <a-space wrap>
          <a-tag>总数 {{ data?.summary.business_counter.notification.total ?? 0 }}</a-tag>
          <a-tag color="green">成功 {{ data?.summary.business_counter.notification.success ?? 0 }}</a-tag>
          <a-tag color="red">失败 {{ data?.summary.business_counter.notification.failure ?? 0 }}</a-tag>
          <a-tag color="blue">运行中 {{ data?.summary.business_counter.notification.running ?? 0 }}</a-tag>
        </a-space>
      </a-card>
    </a-col>
    <a-col :xs="24" :md="12">
      <a-card title="账户注销任务">
        <a-space wrap>
          <a-tag>总数 {{ data?.summary.business_counter.deactivation.total ?? 0 }}</a-tag>
          <a-tag color="green">成功 {{ data?.summary.business_counter.deactivation.success ?? 0 }}</a-tag>
          <a-tag color="red">失败 {{ data?.summary.business_counter.deactivation.failure ?? 0 }}</a-tag>
          <a-tag color="blue">运行中 {{ data?.summary.business_counter.deactivation.running ?? 0 }}</a-tag>
        </a-space>
      </a-card>
    </a-col>
  </a-row>

  <a-card title="状态分布" style="margin-top: 16px">
    <a-space wrap>
      <a-tag color="green">成功 {{ data?.summary.status_counter.success ?? 0 }}</a-tag>
      <a-tag color="red">失败 {{ data?.summary.status_counter.failure ?? 0 }}</a-tag>
      <a-tag color="gold">排队 {{ data?.summary.status_counter.pending ?? 0 }}</a-tag>
      <a-tag color="blue">执行中 {{ data?.summary.status_counter.started ?? 0 }}</a-tag>
      <a-tag color="orange">重试 {{ data?.summary.status_counter.retry ?? 0 }}</a-tag>
      <a-tag>撤销 {{ data?.summary.status_counter.revoked ?? 0 }}</a-tag>
    </a-space>
  </a-card>

  <a-card title="最近任务" style="margin-top: 16px">
    <template #extra>
      <a-space>
        <a-checkbox v-model:checked="onlyFailure">仅失败</a-checkbox>
      </a-space>
    </template>

    <a-table :data-source="tableRows" :pagination="false" row-key="task_id" :loading="loading" :scroll="{ x: 1100 }">
      <a-table-column title="任务ID" data-index="task_id" :width="260" />
      <a-table-column title="任务名" data-index="task_name" :width="260" />
      <a-table-column title="状态" key="status" :width="110">
        <template #default="{ record }">
          <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="完成时间" key="date_done" :width="200">
        <template #default="{ record }">
          {{ formatDateTime(record.date_done) }}
        </template>
      </a-table-column>
      <a-table-column title="结果摘要" key="result" :ellipsis="true">
        <template #default="{ record }">
          <span>{{ record.result_preview || '-' }}</span>
        </template>
      </a-table-column>
      <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" @click="openDetail(record)">详情</a-button>
          </TableHoverActions>
        </template>
      </a-table-column>
    </a-table>
  </a-card>

  <a-drawer v-model:open="detailOpen" title="任务详情" width="760">
    <a-descriptions v-if="activeTask" bordered :column="1" size="small">
      <a-descriptions-item label="任务ID">{{ activeTask.task_id }}</a-descriptions-item>
      <a-descriptions-item label="任务名">{{ activeTask.task_name }}</a-descriptions-item>
      <a-descriptions-item label="状态">
        <a-tag :color="statusColor(activeTask.status)">{{ activeTask.status }}</a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="完成时间">{{ formatDateTime(activeTask.date_done) }}</a-descriptions-item>
    </a-descriptions>

    <a-divider />
    <div style="font-weight: 600; margin-bottom: 6px">结果</div>
    <pre class="detail-block">{{ activeTask?.result || '-' }}</pre>

    <div style="font-weight: 600; margin: 10px 0 6px">错误堆栈</div>
    <pre class="detail-block">{{ activeTask?.traceback || '-' }}</pre>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { fetchTaskDashboard, type TaskSummaryResponse } from '../api/modules/tasks';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { formatDateTime } from '../utils/datetime';

const loading = ref(false);
const data = ref<TaskSummaryResponse | null>(null);
const lastUpdatedText = ref('-');
const autoRefresh = ref(true);
const onlyFailure = ref(false);
const detailOpen = ref(false);
const activeTask = ref<TaskSummaryResponse['recent_tasks'][number] | null>(null);

const query = ref({
  window_hours: 24,
  limit: 20,
});

const tableRows = computed(() => {
  const rows = data.value?.recent_tasks || [];
  if (!onlyFailure.value) return rows;
  return rows.filter((r) => r.status === 'FAILURE');
});

const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: 1,
    min: 60,
  }),
);

function statusColor(status: string) {
  if (status === 'SUCCESS') return 'green';
  if (status === 'FAILURE') return 'red';
  if (status === 'STARTED') return 'blue';
  if (status === 'RETRY') return 'orange';
  if (status === 'PENDING') return 'gold';
  return 'default';
}

async function load() {
  try {
    loading.value = true;
    data.value = await fetchTaskDashboard(query.value);
    lastUpdatedText.value = formatDateTime(new Date());
  } finally {
    loading.value = false;
  }
}

function openDetail(row: TaskSummaryResponse['recent_tasks'][number]) {
  activeTask.value = row;
  detailOpen.value = true;
}

let timer: number | null = null;

function startTimer() {
  stopTimer();
  if (!autoRefresh.value) return;
  timer = window.setInterval(() => {
    load();
  }, 15000);
}

function stopTimer() {
  if (timer) {
    window.clearInterval(timer);
    timer = null;
  }
}

watch(autoRefresh, () => startTimer());

onMounted(async () => {
  await load();
  startTimer();
});

onUnmounted(() => stopTimer());
</script>

<style scoped>
.detail-block {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  background: #f7f7f7;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
