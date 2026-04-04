<template>
  <a-space style="margin-bottom: 16px">
    <a-select v-model:value="query.status" style="width: 180px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="pending">待审批</a-select-option>
      <a-select-option value="active">已通过</a-select-option>
      <a-select-option value="rejected">已拒绝</a-select-option>
      <a-select-option value="expired">已回收</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="申请人" data-index="applicant" />
    <a-table-column title="状态" data-index="status" />
    <a-table-column title="试用到期时间" data-index="expires_at" />
    <a-table-column title="创建时间" data-index="created_at" />
    <a-table-column title="操作" key="actions">
      <template #default="{ record }">
        <a-space>
          <a-button v-if="canApprove" size="small" @click="doAction(record.id, 'approve')">通过</a-button>
          <a-button v-if="canReject" size="small" danger @click="doAction(record.id, 'reject')">拒绝</a-button>
          <a-button v-if="canRecycle" size="small" @click="doAction(record.id, 'recycle')">回收权限</a-button>
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
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchAITrials, trialAction, type TrialApplicationItem } from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<TrialApplicationItem[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, status: '' });

const canApprove = computed(() => auth.hasPermission('button:ai:trial:approve'));
const canReject = computed(() => auth.hasPermission('button:ai:trial:reject'));
const canRecycle = computed(() => auth.hasPermission('button:ai:trial:recycle'));

async function load() {
  try {
    loading.value = true;
    const data = await fetchAITrials(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function doAction(id: number, action: 'approve' | 'reject' | 'recycle') {
  try {
    await trialAction(id, action);
    message.success('操作成功');
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
