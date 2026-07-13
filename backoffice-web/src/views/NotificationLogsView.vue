<template>
  <div class="page-header">
    <div>
      <div class="page-title">{{ pageTitle }}</div>
      <div class="page-desc">{{ pageDesc }}</div>
    </div>
  </div>

  <a-card :bordered="false" class="filter-card">
    <a-space wrap>
      <a-input-search
        v-model:value="query.q"
        :placeholder="isSms ? '用户/手机号/BizId/RequestId' : '用户/收件人/标题'"
        enter-button
        @search="load"
        style="width: 320px"
      />
      <a-select v-model:value="query.status" style="width: 150px" @change="load">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option value="queued">已入队</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="accepted">已受理</a-select-option>
        <a-select-option value="delivered">已送达</a-select-option>
        <a-select-option value="sent">已发送</a-select-option>
        <a-select-option value="partial">部分成功</a-select-option>
        <a-select-option value="failed">失败</a-select-option>
        <a-select-option value="skipped">跳过</a-select-option>
      </a-select>
      <a-button type="primary" @click="load">查询</a-button>
      <a-button @click="reset">重置</a-button>
    </a-space>
  </a-card>

  <a-card :bordered="false" class="table-card">
    <a-table
      :data-source="rows"
      :pagination="false"
      row-key="id"
      :loading="loading"
      :scroll="tableScroll"
      size="middle"
    >
      <template v-if="isSms">
        <a-table-column title="Delivery ID" data-index="delivery_id" :width="110" />
        <a-table-column title="业务类型" data-index="business_type" :width="140">
          <template #default="{ record }">{{ businessTypeLabel(record.business_type || record.business_scene) }}</template>
        </a-table-column>
        <a-table-column title="用户/登录前用户" data-index="recipient_display" :width="160" />
        <a-table-column title="收件人" data-index="masked_phone" :width="150" />
        <a-table-column title="模板编码" data-index="template_code" :width="150">
          <template #default="{ text }">{{ text || '-' }}</template>
        </a-table-column>
        <a-table-column title="提交状态" data-index="submit_status" :width="110">
          <template #default="{ text }"><a-tag :color="submitStatusColor(text)">{{ submitStatusLabel(text) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="送达状态" data-index="delivery_status" :width="110">
          <template #default="{ text }"><a-tag :color="deliveryStatusColor(text)">{{ deliveryStatusLabel(text) }}</a-tag></template>
        </a-table-column>
        <a-table-column title="Code/ErrCode" data-index="code_err_code" :width="140">
          <template #default="{ text }">{{ text || '-' }}</template>
        </a-table-column>
        <a-table-column title="BizId" data-index="biz_id" :width="180">
          <template #default="{ text }">{{ text || '-' }}</template>
        </a-table-column>
        <a-table-column title="提交时间" :width="180">
          <template #default="{ record }">{{ formatDateTime(record.submitted_at || record.sent_at) }}</template>
        </a-table-column>
        <a-table-column title="回执时间" :width="180">
          <template #default="{ record }">{{ formatDateTime(record.receipt_at || record.delivered_at) }}</template>
        </a-table-column>
      </template>
      <template v-else>
        <a-table-column title="ID" data-index="id" :width="80" />
        <a-table-column title="渠道" data-index="channel" :width="100" />
        <a-table-column title="业务类型" data-index="business_type" :width="150">
          <template #default="{ record }">{{ businessTypeLabel(record.business_type || record.business_scene) }}</template>
        </a-table-column>
        <a-table-column title="用户" data-index="user_name" :width="180">
          <template #default="{ record }">{{ record.user_name || '-' }}</template>
        </a-table-column>
        <a-table-column title="收件人" key="recipient" :width="180">
          <template #default="{ record }">
            {{ record.recipient_key || record.receiver_phone || record.receiver_email || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="状态" key="status" :width="110">
          <template #default="{ record }">
            <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="标题" data-index="title" :width="220" />
        <a-table-column title="结果" key="result" :width="140">
          <template #default="{ record }">{{ record.success_count }}/{{ record.target_count }}</template>
        </a-table-column>
        <a-table-column title="发送时间" key="sent_at" :width="190">
          <template #default="{ record }">
            {{ formatDateTime(record.sent_at) }}
          </template>
        </a-table-column>
      </template>
      <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" @click="openDetail(record.id)">查看</a-button>
            <a-button
              v-if="isSms"
              size="small"
              type="link"
              :loading="queryingId === record.id"
              :disabled="!record.biz_id"
              @click="querySmsReceipt(record.id)"
            >
              查询回执
            </a-button>
          </TableHoverActions>
        </template>
      </a-table-column>
    </a-table>

    <a-pagination
      class="table-pagination"
      :current="query.page"
      :page-size="query.page_size"
      :total="pagination.total"
      @change="onPageChange"
    />
  </a-card>

  <a-modal v-model:open="detailOpen" title="通知详情" :footer="null" width="780px">
      <a-descriptions v-if="detail" :column="2" bordered size="small">
      <a-descriptions-item label="日志ID">{{ detail.id }}</a-descriptions-item>
      <a-descriptions-item v-if="isSms" label="Delivery ID">{{ detail.delivery_id || '-' }}</a-descriptions-item>
      <a-descriptions-item :label="isSms ? '用户' : '用户'">{{ isSms ? (detail.recipient_display || '-') : (detail.recipient_display || detail.user_name || '-') }}</a-descriptions-item>
      <a-descriptions-item label="收件人类型">{{ detail.recipient_type }}</a-descriptions-item>
      <a-descriptions-item label="收件人">{{ isSms ? (detail.masked_phone || '-') : (detail.recipient_key || detail.receiver_phone || detail.receiver_email || '-') }}</a-descriptions-item>
      <a-descriptions-item label="渠道">{{ detail.channel }}</a-descriptions-item>
      <a-descriptions-item label="状态">{{ statusLabel(detail.status) }}</a-descriptions-item>
      <a-descriptions-item label="业务类型">{{ businessTypeLabel(detail.business_type || detail.business_scene) }}</a-descriptions-item>
      <a-descriptions-item label="业务场景">{{ businessSceneLabel(detail.business_scene) }}</a-descriptions-item>
      <a-descriptions-item label="业务域">{{ businessDomainLabel(detail.business_domain) }}</a-descriptions-item>
      <a-descriptions-item label="业务ID">{{ detail.business_id || '-' }}</a-descriptions-item>
      <a-descriptions-item v-if="isSms" label="模板编码">{{ detail.template_code || '-' }}</a-descriptions-item>
      <a-descriptions-item v-if="isSms" label="提交状态">{{ submitStatusLabel(detail.submit_status) }}</a-descriptions-item>
      <a-descriptions-item v-if="isSms" label="送达状态">{{ deliveryStatusLabel(detail.delivery_status) }}</a-descriptions-item>
      <a-descriptions-item label="标题" :span="2">{{ detail.title || '-' }}</a-descriptions-item>
      <a-descriptions-item label="内容" :span="2">{{ detail.body || '-' }}</a-descriptions-item>
      <a-descriptions-item label="成功/目标">{{ detail.success_count }}/{{ detail.target_count }}</a-descriptions-item>
      <a-descriptions-item label="失败数">{{ detail.failure_count }}</a-descriptions-item>
      <a-descriptions-item label="BizId/Provider ID">{{ detail.biz_id || detail.provider_message_id || '-' }}</a-descriptions-item>
      <a-descriptions-item label="Provider 请求ID">{{ detail.provider_request_id || '-' }}</a-descriptions-item>
      <a-descriptions-item label="Code/ErrCode">{{ detail.code_err_code || detail.provider_code || '-' }}</a-descriptions-item>
      <a-descriptions-item label="Provider 状态">{{ detail.provider_status || '-' }}</a-descriptions-item>
      <a-descriptions-item label="请求ID">{{ detail.request_id || '-' }}</a-descriptions-item>
      <a-descriptions-item label="提交时间">{{ formatDateTime(detail.submitted_at || detail.sent_at) }}</a-descriptions-item>
      <a-descriptions-item label="回执时间">{{ formatDateTime(detail.receipt_at || detail.delivered_at) }}</a-descriptions-item>
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
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { useRoute } from 'vue-router';
import { fetchNotificationLogDetail, fetchNotificationLogs, querySmsSendDetails, type NotificationMessageLog } from '../api/modules/notifications';
import TableHoverActions from '../components/TableHoverActions.vue';
import type { Pagination } from '../types';
import { formatDateTime } from '../utils/datetime';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const route = useRoute();
const channel = (route.meta.channel as 'all' | 'apns' | 'email' | 'sms') || 'all';
const isSms = computed(() => channel === 'sms');
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: isSms.value ? 2 : 1,
    min: 96,
  }),
);

const loading = ref(false);
const queryingId = ref<number | null>(null);
const rows = ref<NotificationMessageLog[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  status: '' as '' | 'queued' | 'processing' | 'accepted' | 'delivered' | 'sent' | 'failed' | 'partial' | 'skipped',
});

const detailOpen = ref(false);
const detail = ref<NotificationMessageLog | null>(null);
const pageTitle = computed(() => {
  if (channel === 'sms') return '通知中心 / 短信发送记录';
  if (channel === 'email') return '通知中心 / 邮箱发送记录';
  if (channel === 'apns') return '通知中心 / APNs 发送记录';
  return '通知中心 / 全渠道记录';
});
const pageDesc = computed(() => {
  if (channel === 'sms') return '统一短信台账视图，使用固定列宽并支持横向独立滚动。';
  return '统一通知投递记录视图，支持按渠道、收件人和状态快速检索。';
});
const tableScroll = computed(() => (isSms.value ? { x: 1560 } : { x: 1370 }));

function normalizedValue(value: unknown) {
  return String(value ?? '').trim();
}

function businessTypeLabel(type: unknown) {
  const raw = normalizedValue(type);
  if (!raw) return '-';
  const normalized = raw.toLowerCase();
  const labels: Record<string, string> = {
    'account.auth': '账号认证',
    'account.lifecycle': '账号生命周期',
    'operation.campaign': '运营活动',
    'membership.pro_trial': '会员试用',
    'medical.resource': '医疗资料',
    login_otp: '登录验证码',
  };
  return labels[normalized] || raw;
}

function businessSceneLabel(scene: unknown) {
  const raw = normalizedValue(scene);
  if (!raw) return '-';
  const normalized = raw.toLowerCase();
  const labels: Record<string, string> = {
    'account.auth.login_otp_requested': '登录验证码',
    'account.auth.phone_otp_requested': '手机号验证码',
    'account.lifecycle.deactivation_otp_requested': '注销账户验证码',
    'account.lifecycle.deactivation_completed': '账户注销完成',
    'operation.campaign.manual_send': '手动群发活动',
    'membership.pro_trial.application_approved': '试用会员申请通过',
    'membership.pro_trial.application_rejected': '试用会员申请驳回',
    'membership.pro_trial.manually_granted': '手动开通试用会员',
    'medical.resource.updated': '医疗资料更新',
  };
  return labels[normalized] || raw;
}

function businessDomainLabel(domain: unknown) {
  const raw = normalizedValue(domain);
  if (!raw) return '-';
  const normalized = raw.toLowerCase();
  const labels: Record<string, string> = {
    account: '账号',
    operation: '运营',
    membership: '会员',
    medical: '医疗',
  };
  return labels[normalized] || raw;
}

function statusColor(status: string) {
  const normalized = normalizedValue(status).toLowerCase();
  if (normalized === 'queued' || normalized === 'processing') return 'blue';
  if (normalized === 'accepted') return 'cyan';
  if (normalized === 'delivered') return 'green';
  if (normalized === 'sent') return 'green';
  if (normalized === 'partial') return 'orange';
  if (normalized === 'failed') return 'red';
  return 'default';
}

function statusLabel(status: string) {
  const normalized = normalizedValue(status).toLowerCase();
  if (normalized === 'queued') return '已入队';
  if (normalized === 'processing') return '处理中';
  if (normalized === 'accepted') return '已受理';
  if (normalized === 'delivered') return '已送达';
  if (normalized === 'sent') return '已发送';
  if (normalized === 'partial') return '部分成功';
  if (normalized === 'failed') return '失败';
  if (normalized === 'skipped') return '跳过';
  return status;
}

function submitStatusColor(status: unknown) {
  const normalized = normalizedValue(status).toLowerCase();
  if (['accepted', 'submitted', 'success', 'ok', '0', '1', '3'].includes(normalized)) return 'green';
  if (['queued', 'created', 'processing'].includes(normalized)) return 'blue';
  if (['unknown', 'submit_unknown'].includes(normalized)) return 'orange';
  if (['failed', 'submit_failed', '2'].includes(normalized)) return 'red';
  return 'default';
}

function submitStatusLabel(status: unknown) {
  const raw = normalizedValue(status);
  const normalized = raw.toLowerCase();
  const labels: Record<string, string> = {
    accepted: '已提交',
    submitted: '已提交',
    success: '已提交',
    ok: '已提交',
    '0': '已提交',
    '1': '已提交',
    '3': '已提交',
    queued: '待提交',
    created: '待提交',
    processing: '提交中',
    unknown: '提交未知',
    submit_unknown: '提交未知',
    failed: '提交失败',
    submit_failed: '提交失败',
    '2': '提交失败',
  };
  return labels[normalized] || raw || '-';
}

function deliveryStatusColor(status: unknown) {
  const normalized = normalizedValue(status).toLowerCase();
  if (['delivered', 'success', 'delivered_to_terminal', '3'].includes(normalized)) return 'green';
  if (['pending', 'accepted', 'submitted', 'queued', 'processing', '1'].includes(normalized)) return 'blue';
  if (['unknown', 'submit_unknown'].includes(normalized)) return 'orange';
  if (['failed', 'delivery_failed', 'submit_failed', '2'].includes(normalized)) return 'red';
  return 'default';
}

function deliveryStatusLabel(status: unknown) {
  const raw = normalizedValue(status);
  const normalized = raw.toLowerCase();
  const labels: Record<string, string> = {
    delivered: '已送达',
    success: '已送达',
    delivered_to_terminal: '已送达',
    '3': '已送达',
    pending: '待回执',
    accepted: '待回执',
    submitted: '待回执',
    queued: '待回执',
    processing: '待回执',
    '1': '待回执',
    unknown: '回执未知',
    submit_unknown: '回执未知',
    failed: '送达失败',
    delivery_failed: '送达失败',
    '2': '送达失败',
    submit_failed: '无回执（提交失败）',
    cancelled: '已取消',
    expired: '已过期',
  };
  return labels[normalized] || raw || '-';
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

function reset() {
  query.page = 1;
  query.page_size = 20;
  query.q = '';
  query.status = '';
  void load();
}

async function openDetail(logId: number) {
  const data = await fetchNotificationLogDetail(logId);
  detail.value = data;
  detailOpen.value = true;
}

async function querySmsReceipt(logId: number) {
  queryingId.value = logId;
  try {
    const data = await querySmsSendDetails(logId);
    const index = rows.value.findIndex((row) => row.id === logId);
    if (index >= 0) {
      rows.value[index] = data;
    }
    if (detail.value?.id === logId) {
      detail.value = data;
    }
    message.success('已查询并更新短信回执状态');
  } finally {
    queryingId.value = null;
  }
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f1f1f;
}

.page-desc {
  margin-top: 4px;
  color: #8c8c8c;
  font-size: 13px;
}

.filter-card {
  margin-bottom: 12px;
}

.table-card {
  overflow: hidden;
}

.table-pagination {
  margin-top: 16px;
  text-align: right;
}

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
