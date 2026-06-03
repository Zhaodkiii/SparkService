<template>
  <a-card :bordered="false" style="margin-bottom: 16px">
    <a-space wrap>
      <a-button :loading="loading" @click="loadStatus">刷新状态</a-button>
      <a-switch v-model:checked="autoRefresh" checked-children="自动刷新" un-checked-children="手动刷新" />
      <span style="color: #999">上次刷新：{{ lastUpdatedText }}</span>
    </a-space>
  </a-card>

  <a-row :gutter="16">
    <a-col :xs="24" :sm="12" :md="6">
      <a-card title="Worker">
        <a-space>
          <a-tag :color="status?.worker.running ? 'green' : 'red'">{{ status?.worker.running ? '运行中' : '未运行' }}</a-tag>
          <span>PID: {{ status?.worker.pid ?? '-' }}</span>
        </a-space>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="6">
      <a-card title="Beat">
        <a-space>
          <a-tag :color="status?.beat.running ? 'green' : 'red'">{{ status?.beat.running ? '运行中' : '未运行' }}</a-tag>
          <span>PID: {{ status?.beat.pid ?? '-' }}</span>
        </a-space>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="6">
      <a-card title="Ping">
        <a-space>
          <a-tag :color="status?.ping.healthy ? 'green' : 'orange'">{{ status?.ping.healthy ? '可通信' : '不可通信' }}</a-tag>
          <span>Host: {{ status?.host ?? '-' }}</span>
        </a-space>
      </a-card>
    </a-col>
    <a-col :xs="24" :sm="12" :md="6">
      <a-card title="Redis (Broker)">
        <a-space>
          <a-tag :color="status?.redis?.healthy ? 'green' : 'orange'">{{ status?.redis?.healthy ? '可连接' : '不可连接' }}</a-tag>
          <span>{{ status?.redis?.display ?? '-' }}</span>
        </a-space>
      </a-card>
    </a-col>
  </a-row>

  <a-card title="异步任务管理" style="margin-top: 16px">
    <template #extra>
      <a-space>
        <a-button type="primary" :disabled="!canControl" :loading="actionLoading === 'start'" @click="doControl('start')">启动 Celery</a-button>
        <a-button danger :disabled="!canControl" :loading="actionLoading === 'stop'" @click="doControl('stop')">停止 Celery</a-button>
        <a-button :disabled="!canControl" :loading="actionLoading === 'restart'" @click="doControl('restart')">重启 Celery</a-button>
        <a-button
          :disabled="!canControl || !status || !!status.redis?.healthy || !redisManageable"
          :loading="actionLoading === 'start_redis'"
          @click="doControl('start_redis')"
        >
          启动 Redis
        </a-button>
        <a-button
          danger
          :disabled="!canControl || !status || !status.redis?.healthy || !redisManageable"
          :loading="actionLoading === 'stop_redis'"
          @click="doControl('stop_redis')"
        >
          停止 Redis
        </a-button>
      </a-space>
    </template>

    <a-alert
      v-if="!canControl"
      type="warning"
      show-icon
      style="margin-bottom: 12px"
      message="当前账号没有“异步任务启停”权限，仅可查看状态"
    />

    <a-descriptions bordered :column="1" size="small">
      <a-descriptions-item label="总体状态">
        <a-tag :color="status?.overall_running ? 'green' : 'red'">{{ status?.overall_running ? 'Worker+Beat 均运行' : '部分/全部未运行' }}</a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="run 目录">{{ status?.run_dir ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="log 目录">{{ status?.log_dir ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="ping 输出">{{ status?.ping.output || '-' }}</a-descriptions-item>
      <a-descriptions-item label="ping 错误">{{ status?.ping.error || '-' }}</a-descriptions-item>
      <a-descriptions-item label="Redis (Broker)">{{ status?.redis?.display ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="Redis 错误">{{ status?.redis?.error || '-' }}</a-descriptions-item>
    </a-descriptions>

    <a-divider />
    <div style="font-weight: 600; margin-bottom: 8px">最近操作记录</div>
    <a-table :data-source="operationRows" row-key="id" :pagination="false" size="small">
      <a-table-column title="时间" key="time" :width="200">
        <template #default="{ record }">
          {{ formatDateTime(record.time) }}
        </template>
      </a-table-column>
      <a-table-column title="动作" data-index="action" :width="100" />
      <a-table-column title="组件" data-index="name" :width="150" />
      <a-table-column title="结果" data-index="result" :width="180" />
      <a-table-column title="PID" data-index="pid" :width="100" />
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import { controlTaskManager, fetchTaskManagerStatus, type TaskManagerStatusResponse } from '../api/modules/tasks';
import { useAuthStore } from '../stores/auth';
import { formatDateTime } from '../utils/datetime';

type ActionType = 'start' | 'stop' | 'restart' | 'start_redis' | 'stop_redis';

const auth = useAuthStore();
const canControl = computed(() => auth.hasPermission('button:tasks:manager:control'));
const redisManageable = computed(() => {
  const r = status.value?.redis;
  if (!r) return false;
  return r.local_manageable === true || r.local_start_available === true;
});
const loading = ref(false);
const actionLoading = ref<ActionType | ''>('');
const status = ref<TaskManagerStatusResponse | null>(null);
const autoRefresh = ref(true);
const lastUpdatedText = ref('-');
const operationRows = ref<Array<{ id: string; time: string | Date; action: string; name: string; result: string; pid: string }>>([]);

async function loadStatus() {
  try {
    loading.value = true;
    status.value = await fetchTaskManagerStatus();
    lastUpdatedText.value = formatDateTime(new Date());
  } finally {
    loading.value = false;
  }
}

async function doControl(action: ActionType) {
  if (!canControl.value) {
    message.warning('没有操作权限');
    return;
  }
  try {
    actionLoading.value = action;
    const resp = await controlTaskManager(action);
    status.value = resp.status;
    lastUpdatedText.value = formatDateTime(new Date());
    const now = new Date();
    const rows = resp.operations.map((item, idx) => ({
      id: `${Date.now()}-${idx}`,
      time: now,
      action: action.toUpperCase(),
      name: item.name,
      result: item.action,
      pid: item.pid ? String(item.pid) : '-',
    }));
    operationRows.value = [...rows, ...operationRows.value].slice(0, 20);
    if (action === 'start_redis') {
      const op = resp.operations.find((item) => item.name === 'redis');
      const r = op?.action ?? '';
      const ok = r === 'already_running' || r.startsWith('started_');
      if (ok) {
        if (r === 'already_running') {
          message.info('Redis 已在运行');
        } else {
          message.success('Redis 已就绪');
        }
      } else {
        message.warning(`Redis: ${r || '未知结果'}`);
      }
    } else if (action === 'stop_redis') {
      const op = resp.operations.find((item) => item.name === 'redis');
      const r = op?.action ?? '';
      const ok = r === 'already_stopped' || r.startsWith('stopped');
      if (ok) {
        if (r === 'already_stopped') {
          message.info('Redis 已处于停止状态');
        } else {
          message.success('Redis 已停止');
        }
      } else {
        message.warning(`Redis: ${r || '未知结果'}`);
      }
    } else {
      message.success(`操作完成: ${action}`);
    }
  } finally {
    actionLoading.value = '';
  }
}

let timer: number | null = null;

function startTimer() {
  stopTimer();
  if (!autoRefresh.value) return;
  timer = window.setInterval(() => {
    loadStatus();
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
  await loadStatus();
  startTimer();
});

onUnmounted(() => stopTimer());
</script>
