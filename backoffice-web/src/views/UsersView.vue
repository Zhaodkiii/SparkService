<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="用户名/邮箱" enter-button @search="load" style="width: 280px" />
    <a-select v-model:value="query.is_active" style="width: 140px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="true">启用</a-select-option>
      <a-select-option value="false">禁用</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" />
    <a-table-column title="用户名" data-index="username" />
    <a-table-column title="邮箱" data-index="email" />
    <a-table-column title="状态" key="status">
      <template #default="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '禁用' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button v-if="canUpdate" size="small" @click="onToggleStatus(record.id, !record.is_active)">
            {{ record.is_active ? '禁用' : '启用' }}
          </a-button>
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
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchUsers, updateUserStatus } from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import type { AdminUser, Pagination } from '../types';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<AdminUser[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  is_active: '',
});

const canUpdate = computed(() => auth.hasPermission('button:user:status:update'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: canUpdate.value ? 1 : 0,
    min: 60,
  }),
);

async function load() {
  try {
    loading.value = true;
    const data = await fetchUsers(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function onToggleStatus(userId: number, isActive: boolean) {
  try {
    await updateUserStatus(userId, isActive);
    message.success('用户状态已更新');
    await load();
  } catch (error: any) {
    message.error(error?.message || '更新失败');
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
