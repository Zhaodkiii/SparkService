<template>
  <a-space style="margin-bottom: 12px">
    <a-input-search v-model:value="query.q" placeholder="活动名/标题" enter-button @search="load" style="width: 320px" />
    <a-select v-model:value="query.status" style="width: 150px" @change="load" allow-clear placeholder="状态">
      <a-select-option value="queued">待发送</a-select-option>
      <a-select-option value="scheduled">定时中</a-select-option>
      <a-select-option value="running">发送中</a-select-option>
      <a-select-option value="completed">已完成</a-select-option>
      <a-select-option value="failed">失败</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" :width="80" />
    <a-table-column title="活动名" data-index="name" :width="180" />
    <a-table-column title="状态" key="status" :width="120">
      <template #default="{ record }">
        <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="模板" data-index="template_name" :width="140" />
    <a-table-column title="渠道" key="channels" :width="180">
      <template #default="{ record }">
        <a-space>
          <a-tag v-for="c in record.channels" :key="c">{{ c }}</a-tag>
        </a-space>
      </template>
    </a-table-column>
    <a-table-column title="目标" data-index="target_count" :width="90" />
    <a-table-column title="成功" data-index="success_count" :width="90" />
    <a-table-column title="失败" data-index="failure_count" :width="90" />
    <a-table-column title="定时" data-index="scheduled_at" :width="190" />
    <a-table-column title="创建时间" data-index="created_at" :width="190" />
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
import { onMounted, reactive, ref } from 'vue';
import { fetchNotificationCampaigns, type NotificationCampaign } from '../api/modules/notifications';
import type { Pagination } from '../types';

const loading = ref(false);
const rows = ref<NotificationCampaign[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  status: '' as string,
});

function statusColor(status: string) {
  if (status === 'completed') return 'green';
  if (status === 'running') return 'blue';
  if (status === 'scheduled') return 'gold';
  if (status === 'failed') return 'red';
  return 'default';
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    queued: '待发送',
    scheduled: '定时中',
    running: '发送中',
    completed: '已完成',
    failed: '失败',
  };
  return map[status] || status;
}

async function load() {
  try {
    loading.value = true;
    const data = await fetchNotificationCampaigns(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
