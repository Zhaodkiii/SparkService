<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="用户名/邮箱/请求ID" enter-button @search="load" style="width: 320px" />
    <a-select v-model:value="query.state" style="width: 180px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="scheduled">scheduled</a-select-option>
      <a-select-option value="frozen">frozen</a-select-option>
      <a-select-option value="anonymized">anonymized</a-select-option>
      <a-select-option value="cleaned_up">cleaned_up</a-select-option>
      <a-select-option value="deactivated">deactivated</a-select-option>
      <a-select-option value="cancelled">cancelled</a-select-option>
      <a-select-option value="failed">failed</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading" :scroll="{ x: 1600 }">
    <a-table-column title="ID" data-index="id" width="80" />
    <a-table-column title="用户" key="user" width="220">
      <template #default="{ record }">
        <div>{{ record.user_name || '-' }}</div>
        <div style="color: #999; font-size: 12px">{{ record.user_email || '-' }}</div>
      </template>
    </a-table-column>
    <a-table-column title="状态" data-index="state" width="120" />
    <a-table-column title="请求时间" data-index="requested_at" width="180" />
    <a-table-column title="完成时间" data-index="completed_at" width="180" />
    <a-table-column title="错误" key="error" width="280">
      <template #default="{ record }">
        <span>{{ record.error_message || '-' }}</span>
      </template>
    </a-table-column>
    <a-table-column title="请求ID" data-index="request_id" width="220" />
    <a-table-column title="操作" key="actions" width="280" fixed="right">
      <template #default="{ record }">
        <a-space>
          <a-button size="small" @click="openAudits(record.id)">审计</a-button>
          <a-button
            v-if="canCancel"
            size="small"
            danger
            :disabled="record.state === 'deactivated' || record.state === 'cancelled'"
            @click="onCancel(record.id)"
          >
            取消
          </a-button>
          <a-button
            v-if="canRetry"
            size="small"
            :disabled="record.state === 'deactivated' || record.state === 'cancelled'"
            @click="onRetry(record.id)"
          >
            重试
          </a-button>
        </a-space>
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

  <a-drawer v-model:open="auditDrawerOpen" title="注销审计日志" width="700">
    <a-table :data-source="audits" :pagination="false" row-key="id" size="small">
      <a-table-column title="时间" data-index="created_at" width="180" />
      <a-table-column title="动作" data-index="action" width="160" />
      <a-table-column title="请求ID" data-index="request_id" width="220" />
      <a-table-column title="详情" key="details">
        <template #default="{ record }">
          <pre style="white-space: pre-wrap; margin: 0">{{ record.details ? JSON.stringify(record.details, null, 2) : '-' }}</pre>
        </template>
      </a-table-column>
    </a-table>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  cancelDeactivation,
  fetchDeactivationAudits,
  fetchDeactivations,
  retryDeactivation,
  type AdminDeactivation,
  type AdminDeactivationAudit,
} from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<AdminDeactivation[]>([]);
const audits = ref<AdminDeactivationAudit[]>([]);
const auditDrawerOpen = ref(false);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  state: '',
});

const canCancel = computed(() => auth.hasPermission('button:user:deactivation:cancel'));
const canRetry = computed(() => auth.hasPermission('button:user:deactivation:retry'));

async function load() {
  try {
    loading.value = true;
    const data = await fetchDeactivations(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function openAudits(deactivationId: number) {
  try {
    audits.value = await fetchDeactivationAudits(deactivationId);
    auditDrawerOpen.value = true;
  } catch (error: any) {
    message.error(error?.message || '加载审计日志失败');
  }
}

async function onCancel(deactivationId: number) {
  try {
    await cancelDeactivation(deactivationId);
    message.success('注销单已取消');
    await load();
  } catch (error: any) {
    message.error(error?.message || '操作失败');
  }
}

async function onRetry(deactivationId: number) {
  try {
    await retryDeactivation(deactivationId);
    message.success('已重新入队处理');
    await load();
  } catch (error: any) {
    message.error(error?.message || '操作失败');
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
