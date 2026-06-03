<template>
  <a-space style="margin-bottom: 16px">
    <a-input-search v-model:value="query.q" placeholder="用户/设备ID/Bundle" enter-button @search="load" style="width: 320px" />
    <a-select v-model:value="query.is_revoked" style="width: 160px" @change="load">
      <a-select-option value="">全部状态</a-select-option>
      <a-select-option value="false">正常</a-select-option>
      <a-select-option value="true">已吊销</a-select-option>
    </a-select>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading" :scroll="{ x: 1400 }">
    <a-table-column title="ID" data-index="id" width="80" />
    <a-table-column title="用户" key="user">
      <template #default="{ record }">
        <div>{{ record.user_name || '-' }}</div>
        <div style="color: #999; font-size: 12px">{{ record.user_email || '-' }}</div>
      </template>
    </a-table-column>
    <a-table-column title="设备ID" data-index="device_id" />
    <a-table-column title="Bundle" data-index="bundle_id" />
    <a-table-column title="平台" data-index="platform" width="100" />
    <a-table-column title="型号" data-index="device_model" />
    <a-table-column title="最后在线" key="last_seen" width="180">
      <template #default="{ record }">
        {{ formatDateTime(record.last_seen) }}
      </template>
    </a-table-column>
    <a-table-column title="状态" key="status" width="100">
      <template #default="{ record }">
        <a-tag :color="record.is_revoked ? 'red' : 'green'">{{ record.is_revoked ? '已吊销' : '正常' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button v-if="canRevoke" size="small" @click="onToggleRevoked(record.id, !record.is_revoked)">
            {{ record.is_revoked ? '恢复' : '吊销' }}
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
import { fetchDevices, updateDeviceRevoked, type AdminDevice } from '../api/modules/users';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { formatDateTime } from '../utils/datetime';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<AdminDevice[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  is_revoked: '',
});

const canRevoke = computed(() => auth.hasPermission('button:user:device:revoke'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: canRevoke.value ? 1 : 0,
    min: 60,
  }),
);

async function load() {
  try {
    loading.value = true;
    const data = await fetchDevices(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function onToggleRevoked(deviceId: number, isRevoked: boolean) {
  try {
    await updateDeviceRevoked(deviceId, isRevoked);
    message.success('设备状态已更新');
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
