<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="设备ID/版本/请求ID" enter-button @search="load" style="width: 300px" />
    <a-select v-model:value="query.platform" style="width: 130px" @change="load">
      <a-select-option value="">全部平台</a-select-option>
      <a-select-option value="iOS">iOS</a-select-option>
      <a-select-option value="Android">Android</a-select-option>
    </a-select>
    <a-select v-model:value="query.has_update" style="width: 140px" @change="load">
      <a-select-option value="">更新状态</a-select-option>
      <a-select-option value="true">有更新</a-select-option>
      <a-select-option value="false">无更新</a-select-option>
    </a-select>
    <a-select v-model:value="query.force_update" style="width: 140px" @change="load">
      <a-select-option value="">强更状态</a-select-option>
      <a-select-option value="true">强更</a-select-option>
      <a-select-option value="false">非强更</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :scroll="{ x: 1600 }">
    <a-table-column title="时间" data-index="checked_at" width="180" />
    <a-table-column title="平台" data-index="platform" width="90" />
    <a-table-column title="Bundle" data-index="bundle_id" :ellipsis="true" />
    <a-table-column title="当前版本" key="current" width="140">
      <template #default="{ record }">{{ versionText(record.current_version, record.current_build) }}</template>
    </a-table-column>
    <a-table-column title="最新版本" key="latest" width="140">
      <template #default="{ record }">{{ versionText(record.latest_version, record.latest_build) || '-' }}</template>
    </a-table-column>
    <a-table-column title="结果" key="result" width="150">
      <template #default="{ record }">
        <a-tag :color="record.has_update ? 'blue' : 'default'">{{ record.has_update ? '有更新' : '无更新' }}</a-tag>
        <a-tag v-if="record.force_update" color="red">强更</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="原因" data-index="decision_reason" width="170" />
    <a-table-column title="用户" data-index="user_name" width="120">
      <template #default="{ record }">{{ record.user_name || '-' }}</template>
    </a-table-column>
    <a-table-column title="设备ID" data-index="device_id" :ellipsis="true" />
    <a-table-column title="IP" data-index="ip_address" width="130" />
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
import { fetchVersionCheckLogs, type VersionCheckLog } from '../api/modules/version';
import type { Pagination } from '../types';

const loading = ref(false);
const rows = ref<VersionCheckLog[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, q: '', platform: '', has_update: '', force_update: '' });

function versionText(version: string, build: string) {
  if (!version) return '';
  return build ? `${version} (${build})` : version;
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchVersionCheckLogs(query);
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
