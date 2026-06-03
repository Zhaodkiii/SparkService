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
    <a-table-column title="状态" key="status">
      <template #default="{ record }">
        <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="试用到期时间" key="expires_at">
      <template #default="{ record }">
        {{ formatDateTime(record.expires_at) }}
      </template>
    </a-table-column>
    <a-table-column title="创建时间" key="created_at">
      <template #default="{ record }">
        {{ formatDateTime(record.created_at) }}
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button v-if="showApprove(record)" size="small" @click="doAction(record.id, 'approve')">通过</a-button>
          <a-button v-if="showReject(record)" size="small" danger @click="doAction(record.id, 'reject')">拒绝</a-button>
          <a-button v-if="showRecycle(record)" size="small" @click="doAction(record.id, 'recycle')">回收权限</a-button>
          <a-button v-if="showGrant(record)" size="small" type="primary" @click="openGrant(record.id)">发放权限</a-button>
          <a-button size="small" @click="openDetail(record.id)">详细</a-button>
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

  <a-modal v-model:open="grantModal.open" title="发放 Pro 试用权限" :confirm-loading="grantModal.loading" @ok="submitGrant">
    <a-form layout="vertical">
      <a-form-item label="试用时长">
        <a-radio-group v-model:value="grantModal.preset">
          <a-radio :value="6">6 天</a-radio>
          <a-radio :value="15">15 天</a-radio>
          <a-radio :value="30">30 天</a-radio>
          <a-radio :value="90">90 天</a-radio>
          <a-radio value="custom">自定义</a-radio>
        </a-radio-group>
      </a-form-item>
      <a-form-item v-if="grantModal.preset === 'custom'" label="自定义天数">
        <a-input-number v-model:value="grantModal.customDays" :min="1" :max="3650" style="width: 100%" />
      </a-form-item>
      <a-form-item label="备注">
        <a-textarea v-model:value="grantModal.note" :maxlength="255" show-count placeholder="可选" />
      </a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="detailModal.open" title="试用详情" :footer="null" width="860px">
    <a-spin :spinning="detailModal.loading">
      <a-descriptions v-if="detailModal.data" bordered :column="2" size="small">
        <a-descriptions-item label="申请人">{{ detailModal.data.applicant }}</a-descriptions-item>
        <a-descriptions-item label="Email">{{ detailModal.data.applicant_email }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="statusColor(detailModal.data.status)">{{ statusLabel(detailModal.data.status) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="授权来源">{{ detailModal.data.grant_source }}</a-descriptions-item>
        <a-descriptions-item label="开始时间">{{ formatDateTime(detailModal.data.started_at) }}</a-descriptions-item>
        <a-descriptions-item label="到期时间">{{ formatDateTime(detailModal.data.expires_at) }}</a-descriptions-item>
        <a-descriptions-item label="备注" :span="2">{{ detailModal.data.note || '-' }}</a-descriptions-item>
      </a-descriptions>

      <div style="margin-top: 16px" />
      <a-descriptions title="最近可信设备" bordered :column="2" size="small">
        <template v-if="detailModal.data?.latest_device">
          <a-descriptions-item label="country_code">{{ detailModal.data.latest_device.country_code || '-' }}</a-descriptions-item>
          <a-descriptions-item label="region_code">{{ detailModal.data.latest_device.region_code || '-' }}</a-descriptions-item>
          <a-descriptions-item label="language_code">{{ detailModal.data.latest_device.language_code || '-' }}</a-descriptions-item>
          <a-descriptions-item label="通知权限">{{ detailModal.data.latest_device.notifications_enabled ? '已开启' : '未开启' }}</a-descriptions-item>
          <a-descriptions-item label="device_id">{{ detailModal.data.latest_device.device_id }}</a-descriptions-item>
          <a-descriptions-item label="bundle_id">{{ detailModal.data.latest_device.bundle_id }}</a-descriptions-item>
          <a-descriptions-item label="platform">{{ detailModal.data.latest_device.platform }}</a-descriptions-item>
          <a-descriptions-item label="system_version">{{ detailModal.data.latest_device.system_version }}</a-descriptions-item>
          <a-descriptions-item label="device_model">{{ detailModal.data.latest_device.device_model }}</a-descriptions-item>
          <a-descriptions-item label="last_seen">{{ formatDateTime(detailModal.data.latest_device.last_seen) }}</a-descriptions-item>
        </template>
        <template v-else>
          <a-descriptions-item label="设备">无</a-descriptions-item>
        </template>
      </a-descriptions>

      <div style="margin-top: 16px" />
      <a-table
        size="small"
        :data-source="detailModal.data?.application_requests || []"
        :pagination="false"
        row-key="id"
        :title="() => '申请流水'"
      >
        <a-table-column title="id" data-index="id" :width="80" />
        <a-table-column title="source" data-index="source" :width="120" />
        <a-table-column title="sequence" data-index="sequence" :width="100" />
        <a-table-column title="status" key="status">
          <template #default="{ record }">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="note" data-index="note" />
        <a-table-column title="created_at" key="created_at" :width="200">
          <template #default="{ record }">
            {{ formatDateTime(record.created_at) }}
          </template>
        </a-table-column>
      </a-table>
    </a-spin>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchAITrialDetail, fetchAITrials, trialAction, type TrialAction, type TrialApplicationItem } from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';
import { formatDateTime } from '../utils/datetime';

const auth = useAuthStore();
const loading = ref(false);
const rows = ref<TrialApplicationItem[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, status: '' });

const canApprove = computed(() => auth.hasPermission('button:ai:trial:approve'));
const canReject = computed(() => auth.hasPermission('button:ai:trial:reject'));
const canRecycle = computed(() => auth.hasPermission('button:ai:trial:recycle'));
const canGrant = computed(() => auth.hasPermission('button:ai:trial:grant'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: Number(canApprove.value) + Number(canReject.value) + Number(canRecycle.value) + Number(canGrant.value) + 1,
    min: 60,
  }),
);

function statusLabel(status: string) {
  switch (status) {
    case 'pending':
      return '待审批';
    case 'active':
      return '已通过';
    case 'rejected':
      return '已拒绝';
    case 'expired':
      return '已回收';
    case 'none':
      return '未开通';
    default:
      return status || '-';
  }
}

function statusColor(status: string) {
  switch (status) {
    case 'pending':
      return 'processing';
    case 'active':
      return 'success';
    case 'rejected':
      return 'error';
    case 'expired':
      return 'default';
    case 'none':
      return 'default';
    default:
      return 'default';
  }
}

function showApprove(row: TrialApplicationItem) {
  return row.status === 'pending' && canApprove.value;
}
function showReject(row: TrialApplicationItem) {
  return row.status === 'pending' && canReject.value;
}
function showRecycle(row: TrialApplicationItem) {
  return row.status === 'active' && canRecycle.value;
}
function showGrant(row: TrialApplicationItem) {
  return (row.status === 'expired' || row.status === 'rejected' || row.status === 'none') && canGrant.value;
}

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

async function doAction(id: number, action: TrialAction, payload: Record<string, unknown> = {}) {
  try {
    await trialAction(id, action, payload);
    message.success('操作成功');
    await load();
  } catch (error: any) {
    message.error(error?.message || '操作失败');
  }
}

const grantModal = reactive({
  open: false,
  loading: false,
  trialId: 0,
  preset: 15 as number | 'custom',
  customDays: 15,
  note: '',
});

function openGrant(trialId: number) {
  grantModal.open = true;
  grantModal.loading = false;
  grantModal.trialId = trialId;
  grantModal.preset = 15;
  grantModal.customDays = 15;
  grantModal.note = '';
}

async function submitGrant() {
  const days = grantModal.preset === 'custom' ? Number(grantModal.customDays) : Number(grantModal.preset);
  if (!days || days < 1) {
    message.error('请输入有效天数');
    return;
  }
  grantModal.loading = true;
  try {
    await doAction(grantModal.trialId, 'grant', { grant_days: days, note: grantModal.note });
    grantModal.open = false;
  } finally {
    grantModal.loading = false;
  }
}

const detailModal = reactive({
  open: false,
  loading: false,
  trialId: 0,
  data: null as TrialApplicationItem | null,
});

async function openDetail(trialId: number) {
  detailModal.open = true;
  detailModal.loading = true;
  detailModal.trialId = trialId;
  detailModal.data = null;
  try {
    detailModal.data = await fetchAITrialDetail(trialId);
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    detailModal.loading = false;
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
