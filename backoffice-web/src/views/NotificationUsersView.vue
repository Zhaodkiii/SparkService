<template>
  <a-card :bordered="false" style="margin-bottom: 12px">
    <a-space wrap>
      <a-input-search v-model:value="query.q" placeholder="用户ID/用户名/邮箱" enter-button @search="load" style="width: 280px" />
      <a-select v-model:value="query.only_enabled" style="width: 130px" @change="load">
        <a-select-option :value="true">仅开通通知</a-select-option>
        <a-select-option :value="false">全部用户</a-select-option>
      </a-select>
      <a-select v-model:value="query.has_apns" style="width: 120px" @change="load" allow-clear placeholder="APNs">
        <a-select-option :value="true">有APNs</a-select-option>
        <a-select-option :value="false">无APNs</a-select-option>
      </a-select>
      <a-select v-model:value="query.has_email" style="width: 120px" @change="load" allow-clear placeholder="邮箱">
        <a-select-option :value="true">有邮箱</a-select-option>
        <a-select-option :value="false">无邮箱</a-select-option>
      </a-select>
      <a-select v-model:value="query.has_sms" style="width: 120px" @change="load" allow-clear placeholder="短信">
        <a-select-option :value="true">有短信</a-select-option>
        <a-select-option :value="false">无短信</a-select-option>
      </a-select>
      <a-button type="primary" :disabled="!canSend" @click="openBatchSend">按条件发送</a-button>
    </a-space>
  </a-card>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" :width="80" />
    <a-table-column title="用户" data-index="username" :width="140" />
    <a-table-column title="邮箱" data-index="email" />
    <a-table-column title="手机号" data-index="phone_number" :width="150" />
    <a-table-column title="APNs设备" key="apns" :width="120">
      <template #default="{ record }">{{ record.enabled_push_devices }}/{{ record.total_devices }}</template>
    </a-table-column>
    <a-table-column title="可用渠道" key="channels" :width="220">
      <template #default="{ record }">
        <a-space>
          <a-tag :color="record.channels.apns ? 'blue' : 'default'">APNs</a-tag>
          <a-tag :color="record.channels.email ? 'green' : 'default'">邮箱</a-tag>
          <a-tag :color="record.channels.sms ? 'orange' : 'default'">短信</a-tag>
        </a-space>
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button type="primary" size="small" :disabled="!canSend" @click="openSingleSend(record)">发送通知</a-button>
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

  <a-modal v-model:open="sendOpen" title="通知发送（极光风格）" :confirm-loading="sending" @ok="submitSend" width="840px">
    <a-form layout="vertical">
      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="发送对象">
            <a-input :value="targetLabel" disabled />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="活动名称（可选）">
            <a-input v-model:value="form.campaign_name" placeholder="例如：春季活动触达" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="通知模板">
            <a-select v-model:value="form.template_id" allow-clear placeholder="选择模板后自动带入文案" @change="onTemplateChange">
              <a-select-option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="发送时间">
            <a-date-picker v-model:value="scheduleAt" show-time style="width: 100%" placeholder="立即发送留空，定时发送请选择时间" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="发送渠道">
        <a-checkbox-group v-model:value="form.channels">
          <a-space>
            <a-checkbox value="apns">iOS APNs</a-checkbox>
            <a-checkbox value="email">邮箱</a-checkbox>
            <a-checkbox value="sms">短信（阿里云）</a-checkbox>
          </a-space>
        </a-checkbox-group>
      </a-form-item>

      <a-form-item label="通知标题">
        <a-input v-model:value="form.title" :maxlength="255" placeholder="支持模板变量，例如 {username}" />
      </a-form-item>
      <a-form-item label="通知内容">
        <a-textarea v-model:value="form.body" :rows="4" placeholder="支持模板变量，例如 {date}" />
      </a-form-item>

      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="APNs Topic（可选）">
            <a-input v-model:value="form.apns_topic" placeholder="留空用默认配置" />
          </a-form-item>
        </a-col>
        <a-col :span="12" v-if="mode === 'batch'">
          <a-form-item label="目标筛选">
            <a-space>
              <a-checkbox v-model:checked="batchFilters.has_apns">有APNs</a-checkbox>
              <a-checkbox v-model:checked="batchFilters.has_email">有邮箱</a-checkbox>
              <a-checkbox v-model:checked="batchFilters.has_sms">有短信</a-checkbox>
              <a-checkbox v-model:checked="batchFilters.only_enabled">仅开通通知</a-checkbox>
            </a-space>
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="附加 Payload（JSON，可选）">
        <a-textarea v-model:value="form.extra_payload_json" :rows="4" placeholder='例如：{"deeplink":"dream://notice/123"}' />
      </a-form-item>

      <a-space>
        <a-button @click="doPreview">预览渲染</a-button>
        <span style="color:#999">预览会以目标用户（或当前管理员）上下文渲染变量</span>
      </a-space>
      <pre v-if="previewText" class="preview-block">{{ previewText }}</pre>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { type Dayjs } from 'dayjs';
import { message } from 'ant-design-vue';
import {
  createNotificationCampaign,
  fetchNotificationTemplates,
  fetchNotificationUsers,
  previewNotification,
  type NotificationTemplate,
  type NotificationUserRow,
} from '../api/modules/notifications';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const auth = useAuthStore();
const canSend = computed(() => auth.hasPermission('button:notification:send'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: canSend.value ? 1 : 0,
    min: 60,
    perButton: 96,
  }),
);

const loading = ref(false);
const sending = ref(false);
const rows = ref<NotificationUserRow[]>([]);
const templates = ref<NotificationTemplate[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const query = reactive({
  page: 1,
  page_size: 20,
  q: '',
  only_enabled: true,
  has_email: undefined as boolean | undefined,
  has_sms: undefined as boolean | undefined,
  has_apns: undefined as boolean | undefined,
});

const sendOpen = ref(false);
const mode = ref<'single' | 'batch'>('single');
const selectedUser = ref<NotificationUserRow | null>(null);
const scheduleAt = ref<Dayjs | null>(null);
const previewText = ref('');

const batchFilters = reactive({
  q: '',
  only_enabled: true,
  has_email: false,
  has_sms: false,
  has_apns: true,
  is_active: true,
});

const form = reactive({
  campaign_name: '',
  template_id: undefined as number | undefined,
  title: '',
  body: '',
  channels: ['apns'] as Array<'apns' | 'email' | 'sms'>,
  apns_topic: '',
  extra_payload_json: '',
});

const targetLabel = computed(() => {
  if (mode.value === 'single' && selectedUser.value) {
    return `${selectedUser.value.username}（ID ${selectedUser.value.id}）`;
  }
  return '按条件筛选用户';
});

async function load() {
  try {
    loading.value = true;
    const data = await fetchNotificationUsers(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function loadTemplates() {
  templates.value = await fetchNotificationTemplates();
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

function resetForm() {
  form.campaign_name = '';
  form.template_id = undefined;
  form.title = '';
  form.body = '';
  form.channels = ['apns'];
  form.apns_topic = '';
  form.extra_payload_json = '';
  scheduleAt.value = null;
  previewText.value = '';
}

function openSingleSend(user: NotificationUserRow) {
  mode.value = 'single';
  selectedUser.value = user;
  resetForm();
  form.channels = [
    ...(user.channels.apns ? ['apns' as const] : []),
    ...(user.channels.email ? ['email' as const] : []),
    ...(user.channels.sms ? ['sms' as const] : []),
  ];
  sendOpen.value = true;
}

function openBatchSend() {
  mode.value = 'batch';
  selectedUser.value = null;
  resetForm();
  sendOpen.value = true;
}

function onTemplateChange(templateId?: number) {
  const tpl = templates.value.find((t) => t.id === templateId);
  if (!tpl) return;
  form.title = tpl.title_template || form.title;
  form.body = tpl.body_template || form.body;
  if (tpl.default_channels?.length) {
    form.channels = tpl.default_channels.filter((v): v is 'apns' | 'email' | 'sms' => ['apns', 'email', 'sms'].includes(v));
  }
}

function parsePayload() {
  let payload: Record<string, unknown> = {};
  if (form.extra_payload_json.trim()) {
    payload = JSON.parse(form.extra_payload_json);
  }
  if (form.apns_topic.trim()) {
    payload.apns_topic = form.apns_topic.trim();
  }
  return payload;
}

async function doPreview() {
  try {
    const payload = parsePayload();
    const data = await previewNotification({
      template_id: form.template_id ?? null,
      user_id: selectedUser.value?.id ?? null,
      title: form.title,
      body: form.body,
      payload,
    });
    previewText.value = `标题：${data.title}\n\n正文：${data.body}\n\nPayload:\n${JSON.stringify(data.payload, null, 2)}`;
  } catch (error: any) {
    message.error(error?.message || '预览失败');
  }
}

async function submitSend() {
  if (!form.channels.length) {
    message.warning('请至少选择一个发送渠道');
    return;
  }
  if (!form.template_id && !form.title.trim() && !form.body.trim()) {
    message.warning('请填写标题或内容，或选择模板');
    return;
  }

  let payload: Record<string, unknown> = {};
  try {
    payload = parsePayload();
  } catch {
    message.error('附加 Payload 不是合法 JSON');
    return;
  }

  try {
    sending.value = true;
    const campaign = await createNotificationCampaign({
      campaign_name: form.campaign_name.trim() || undefined,
      template_id: form.template_id ?? null,
      user_id: mode.value === 'single' ? selectedUser.value?.id ?? null : null,
      channels: form.channels,
      title: form.title.trim() || undefined,
      body: form.body.trim() || undefined,
      payload,
      filters:
        mode.value === 'batch'
          ? {
              ...batchFilters,
              q: (query.q || '').trim(),
            }
          : undefined,
      schedule_at: scheduleAt.value ? scheduleAt.value.toISOString() : null,
    });
    message.success(`已入队发送活动 #${campaign.id}（状态：${campaign.status}）`);
    sendOpen.value = false;
  } catch (error: any) {
    message.error(error?.message || '发送失败');
  } finally {
    sending.value = false;
  }
}

onMounted(async () => {
  await Promise.all([load(), loadTemplates()]);
});
</script>

<style scoped>
.preview-block {
  margin-top: 8px;
  max-height: 220px;
  overflow: auto;
  background: #f7f7f7;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  line-height: 1.5;
}
</style>
