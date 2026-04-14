<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="用户名/邮箱/标题" enter-button @search="load" style="width: 320px" />
    <a-select v-model:value="query.status" style="width: 150px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="sent">已发送</a-select-option>
      <a-select-option value="partial">部分成功</a-select-option>
      <a-select-option value="failed">失败</a-select-option>
      <a-select-option value="skipped">跳过</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" :width="80" />
    <a-table-column title="用户" data-index="user_name" :width="140" />
    <a-table-column title="状态" key="status" :width="110">
      <template #default="{ record }">
        <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="标题" data-index="title" />
    <a-table-column title="结果" key="result" :width="140">
      <template #default="{ record }">{{ record.success_count }}/{{ record.target_count }}</template>
    </a-table-column>
    <a-table-column title="发送时间" data-index="sent_at" :width="190" />
    <a-table-column title="操作" key="actions" :width="120">
      <template #default="{ record }">
        <a-button size="small" @click="openDetail(record.id)">查看</a-button>
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

  <a-modal v-model:open="detailOpen" title="通知详情" :footer="null" width="780px">
    <a-descriptions v-if="detail" :column="2" bordered size="small">
      <a-descriptions-item label="日志ID">{{ detail.id }}</a-descriptions-item>
      <a-descriptions-item label="用户">{{ detail.user_name }}</a-descriptions-item>
      <a-descriptions-item label="渠道">{{ detail.channel }}</a-descriptions-item>
      <a-descriptions-item label="状态">{{ statusLabel(detail.status) }}</a-descriptions-item>
      <a-descriptions-item label="标题" :span="2">{{ detail.title }}</a-descriptions-item>
      <a-descriptions-item label="内容" :span="2">{{ detail.body }}</a-descriptions-item>
      <a-descriptions-item label="成功/目标">{{ detail.success_count }}/{{ detail.target_count }}</a-descriptions-item>
      <a-descriptions-item label="失败数">{{ detail.failure_count }}</a-descriptions-item>
      <a-descriptions-item label="Provider ID">{{ detail.provider_message_id || '-' }}</a-descriptions-item>
      <a-descriptions-item label="请求ID">{{ detail.request_id || '-' }}</a-descriptions-item>
      <a-descriptions-item label="错误信息" :span="2">{{ detail.error_message || '-' }}</a-descriptions-item>
    </a-descriptions>
    <a-divider />
    <div style="font-weight: 600; margin-bottom: 8px">Payload</div>
    <pre class="json-block">{{ pretty(detail?.payload) }}</pre>
    <div style="font-weight: 600; margin: 10px 0 8px">投递明细</div>
    <pre class="json-block">{{ pretty(detail?.delivery_details) }}</pre>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { fetchNotificationLogDetail, fetchNotificationLogs, type NotificationMessageLog } from '../api/modules/notifications';
import type { Pagination } from '../types';

const route = useRoute();
const channel = (route.meta.channel as 'apns' | 'email' | 'sms') || 'apns';

const loading = ref(false);
const rows = ref<NotificationMessageLog[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  status: '' as '' | 'sent' | 'failed' | 'partial' | 'skipped',
});

const detailOpen = ref(false);
const detail = ref<NotificationMessageLog | null>(null);

function statusColor(status: string) {
  if (status === 'sent') return 'green';
  if (status === 'partial') return 'orange';
  if (status === 'failed') return 'red';
  return 'default';
}

function statusLabel(status: string) {
  if (status === 'sent') return '已发送';
  if (status === 'partial') return '部分成功';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '跳过';
  return status;
}

function pretty(data: unknown) {
  try {
    return JSON.stringify(data ?? {}, null, 2);
  } catch {
    return String(data ?? '');
  }
}

async function load() {
  try {
    loading.value = true;
    const data = await fetchNotificationLogs(channel, query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function openDetail(logId: number) {
  const data = await fetchNotificationLogDetail(logId);
  detail.value = data;
  detailOpen.value = true;
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>

<style scoped>
.json-block {
  max-height: 260px;
  overflow: auto;
  padding: 10px;
  background: #f7f7f7;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}
</style>
