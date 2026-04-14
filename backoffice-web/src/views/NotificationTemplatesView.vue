<template>
  <a-space style="margin-bottom: 12px">
    <a-button type="primary" @click="openCreate">新建模板</a-button>
    <a-button @click="load">刷新</a-button>
  </a-space>

  <a-table :data-source="rows" :pagination="false" row-key="id" :loading="loading">
    <a-table-column title="ID" data-index="id" :width="80" />
    <a-table-column title="模板名" data-index="name" :width="180" />
    <a-table-column title="描述" data-index="description" />
    <a-table-column title="默认渠道" key="channels" :width="220">
      <template #default="{ record }">
        <a-space>
          <a-tag v-for="c in record.default_channels" :key="c">{{ c }}</a-tag>
        </a-space>
      </template>
    </a-table-column>
    <a-table-column title="状态" key="active" :width="100">
      <template #default="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'default'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="220">
      <template #default="{ record }">
        <a-space>
          <a-button size="small" @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="确认删除该模板？" @confirm="remove(record.id)">
            <a-button size="small" danger>删除</a-button>
          </a-popconfirm>
        </a-space>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="open" :title="editingId ? '编辑模板' : '新建模板'" :confirm-loading="saving" @ok="save" width="760px">
    <a-form layout="vertical">
      <a-form-item label="模板名">
        <a-input v-model:value="form.name" :disabled="!!editingId" />
      </a-form-item>
      <a-form-item label="描述">
        <a-input v-model:value="form.description" />
      </a-form-item>
      <a-form-item label="默认渠道">
        <a-checkbox-group v-model:value="form.default_channels">
          <a-space>
            <a-checkbox value="apns">APNs</a-checkbox>
            <a-checkbox value="email">邮箱</a-checkbox>
            <a-checkbox value="sms">短信</a-checkbox>
          </a-space>
        </a-checkbox-group>
      </a-form-item>
      <a-form-item label="标题模板">
        <a-input v-model:value="form.title_template" placeholder="支持变量，如 {username}" />
      </a-form-item>
      <a-form-item label="正文模板">
        <a-textarea v-model:value="form.body_template" :rows="5" placeholder="支持变量，如 {date}" />
      </a-form-item>
      <a-form-item label="Payload 模板(JSON)">
        <a-textarea v-model:value="form.payload_template_json" :rows="4" />
      </a-form-item>
      <a-form-item>
        <a-checkbox v-model:checked="form.is_active">启用模板</a-checkbox>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  createNotificationTemplate,
  deleteNotificationTemplate,
  fetchNotificationTemplates,
  updateNotificationTemplate,
  type NotificationTemplate,
} from '../api/modules/notifications';

const loading = ref(false);
const saving = ref(false);
const open = ref(false);
const editingId = ref<number | null>(null);
const rows = ref<NotificationTemplate[]>([]);

const form = reactive({
  name: '',
  description: '',
  title_template: '',
  body_template: '',
  payload_template_json: '{}',
  default_channels: ['apns'] as Array<'apns' | 'email' | 'sms'>,
  is_active: true,
});

function resetForm() {
  form.name = '';
  form.description = '';
  form.title_template = '';
  form.body_template = '';
  form.payload_template_json = '{}';
  form.default_channels = ['apns'];
  form.is_active = true;
}

function openCreate() {
  editingId.value = null;
  resetForm();
  open.value = true;
}

function openEdit(row: NotificationTemplate) {
  editingId.value = row.id;
  form.name = row.name;
  form.description = row.description;
  form.title_template = row.title_template;
  form.body_template = row.body_template;
  form.payload_template_json = JSON.stringify(row.payload_template || {}, null, 2);
  form.default_channels = row.default_channels || [];
  form.is_active = row.is_active;
  open.value = true;
}

async function load() {
  try {
    loading.value = true;
    rows.value = await fetchNotificationTemplates();
  } finally {
    loading.value = false;
  }
}

async function save() {
  let payloadTemplate: Record<string, unknown> = {};
  try {
    payloadTemplate = JSON.parse(form.payload_template_json || '{}');
  } catch {
    message.error('Payload 模板 JSON 格式错误');
    return;
  }

  try {
    saving.value = true;
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      title_template: form.title_template,
      body_template: form.body_template,
      payload_template: payloadTemplate,
      default_channels: form.default_channels,
      is_active: form.is_active,
    };

    if (!payload.name) {
      message.warning('模板名不能为空');
      return;
    }

    if (editingId.value) {
      await updateNotificationTemplate(editingId.value, payload);
      message.success('模板已更新');
    } else {
      await createNotificationTemplate(payload);
      message.success('模板已创建');
    }
    open.value = false;
    await load();
  } catch (error: any) {
    message.error(error?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

async function remove(id: number) {
  try {
    await deleteNotificationTemplate(id);
    message.success('模板已删除');
    await load();
  } catch (error: any) {
    message.error(error?.message || '删除失败');
  }
}

onMounted(load);
</script>
