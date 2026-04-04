<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.action" placeholder="action 关键字" enter-button @search="load" />
    <a-select v-model:value="query.status_code" style="width: 140px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="200">200</a-select-option>
      <a-select-option value="201">201</a-select-option>
      <a-select-option value="400">400</a-select-option>
      <a-select-option value="401">401</a-select-option>
      <a-select-option value="403">403</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id">
    <a-table-column title="时间" data-index="created_at" />
    <a-table-column title="用户" data-index="user_name" />
    <a-table-column title="动作" data-index="action" />
    <a-table-column title="资源" data-index="resource_type" />
    <a-table-column title="状态" data-index="status_code" />
    <a-table-column title="路径" data-index="path" />
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
import { fetchAuditLogs, type AuditLogItem } from '../api/modules/audit';
import type { Pagination } from '../types';

const rows = ref<AuditLogItem[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, action: '', status_code: '' });

async function load() {
  const data = await fetchAuditLogs(query);
  rows.value = data.items;
  Object.assign(pagination, data.pagination);
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
