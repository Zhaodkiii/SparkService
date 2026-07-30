<template>
  <a-space style="margin-bottom: 16px" wrap>
    <a-input-search v-model:value="query.action" placeholder="action 关键字" enter-button @search="load" style="width: 220px" />
    <a-input-search v-model:value="query.request_id" placeholder="request_id" enter-button @search="load" style="width: 220px" />
    <a-input v-model:value="query.path" placeholder="路径" allow-clear @pressEnter="load" style="width: 220px" />
    <a-input v-model:value="query.resource_type" placeholder="资源类型" allow-clear @pressEnter="load" style="width: 160px" />
    <a-select v-model:value="query.status_code" style="width: 140px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="200">200</a-select-option>
      <a-select-option value="201">201</a-select-option>
      <a-select-option value="400">400</a-select-option>
      <a-select-option value="401">401</a-select-option>
      <a-select-option value="403">403</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading" :scroll="{ x: 1400 }">
    <a-table-column title="时间" key="created_at" width="180">
      <template #default="{ record }">
        {{ formatDateTime(record.created_at) }}
      </template>
    </a-table-column>
    <a-table-column title="用户" data-index="user_name" width="120" />
    <a-table-column title="动作" data-index="action" />
    <a-table-column title="资源" data-index="resource_type" width="120" />
    <a-table-column title="状态" data-index="status_code" width="80" />
    <a-table-column title="request_id" data-index="request_id" :ellipsis="true" />
    <a-table-column title="路径" data-index="path" :ellipsis="true" />
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
import { fetchAuditLogs, type AuditLogItem } from '../../api/modules/audit';
import type { Pagination } from '../../types';
import { formatDateTime } from '../../utils/datetime';

const loading = ref(false);
const rows = ref<AuditLogItem[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({
  page: 1,
  page_size: 20,
  action: '',
  status_code: '',
  request_id: '',
  path: '',
  resource_type: '',
});

async function load() {
  loading.value = true;
  try {
    const data = await fetchAuditLogs(query);
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
