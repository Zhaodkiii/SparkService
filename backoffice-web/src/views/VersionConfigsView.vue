<template>
  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreate" type="primary" @click="openCreate">新增版本配置</a-button>
    <a-select v-model:value="query.platform" style="width: 140px" @change="load">
      <a-select-option value="">全部平台</a-select-option>
      <a-select-option value="iOS">iOS</a-select-option>
      <a-select-option value="Android">Android</a-select-option>
    </a-select>
    <a-select v-model:value="query.channel" style="width: 150px" @change="load">
      <a-select-option value="">全部渠道</a-select-option>
      <a-select-option value="production">production</a-select-option>
      <a-select-option value="testflight">testflight</a-select-option>
      <a-select-option value="internal">internal</a-select-option>
    </a-select>
    <a-input-search v-model:value="query.bundle_id" placeholder="Bundle ID" enter-button @search="load" style="width: 260px" />
  </a-space>

  <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :scroll="{ x: 1500 }">
    <a-table-column title="平台" data-index="platform" width="90" />
    <a-table-column title="Bundle" data-index="bundle_id" :ellipsis="true">
      <template #default="{ record }">{{ record.bundle_id || '*' }}</template>
    </a-table-column>
    <a-table-column title="渠道" data-index="channel" width="120" />
    <a-table-column title="最新版本" key="latest" width="140">
      <template #default="{ record }">{{ versionText(record.latest_version, record.latest_build) }}</template>
    </a-table-column>
    <a-table-column title="强更阈值" key="force" width="140">
      <template #default="{ record }">{{ versionText(record.force_update_min_version, record.force_update_min_build) || '-' }}</template>
    </a-table-column>
    <a-table-column title="灰度" key="gradual" width="120">
      <template #default="{ record }">
        <a-tag :color="record.enable_gradual_release ? 'blue' : 'default'">
          {{ record.enable_gradual_release ? `${record.gradual_release_percentage}%` : '关闭' }}
        </a-tag>
      </template>
    </a-table-column>
    <a-table-column title="状态" key="active" width="90">
      <template #default="{ record }">
        <a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="更新时间" data-index="updated_at" width="180" />
    <a-table-column title="操作" key="actions" width="150" fixed="right">
      <template #default="{ record }">
        <a-space>
          <a-button v-if="canUpdate" size="small" @click="openEdit(record)">编辑</a-button>
          <a-button v-if="canUpdate && record.is_active" size="small" danger @click="onDisable(record.id)">停用</a-button>
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

  <a-modal v-model:open="modalOpen" :title="isCreate ? '新增版本配置' : '编辑版本配置'" width="760px" :confirm-loading="saving" @ok="submit">
    <a-form layout="vertical">
      <a-row :gutter="12">
        <a-col :span="8"><a-form-item label="平台"><a-select v-model:value="form.platform" :options="platformOptions" /></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="渠道"><a-select v-model:value="form.channel" :options="channelOptions" /></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="Bundle ID"><a-input v-model:value="form.bundle_id" placeholder="空表示默认配置" /></a-form-item></a-col>
      </a-row>
      <a-row :gutter="12">
        <a-col :span="12"><a-form-item label="最新版本"><a-input v-model:value="form.latest_version" placeholder="1.2.3" /></a-form-item></a-col>
        <a-col :span="12"><a-form-item label="最新 Build"><a-input v-model:value="form.latest_build" /></a-form-item></a-col>
      </a-row>
      <a-row :gutter="12">
        <a-col :span="12"><a-form-item label="强更最低版本"><a-input v-model:value="form.force_update_min_version" /></a-form-item></a-col>
        <a-col :span="12"><a-form-item label="强更最低 Build"><a-input v-model:value="form.force_update_min_build" /></a-form-item></a-col>
      </a-row>
      <a-form-item label="更新标题"><a-input v-model:value="form.update_title" /></a-form-item>
      <a-form-item label="更新说明"><a-textarea v-model:value="form.update_message" :rows="3" /></a-form-item>
      <a-form-item label="发布说明"><a-textarea v-model:value="form.release_notes" :rows="3" /></a-form-item>
      <a-form-item label="下载地址"><a-input v-model:value="form.download_url" /></a-form-item>
      <a-row :gutter="12">
        <a-col :span="8"><a-form-item label="启用灰度"><a-switch v-model:checked="form.enable_gradual_release" /></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="灰度比例"><a-input-number v-model:value="form.gradual_release_percentage" :min="0" :max="100" style="width: 100%" /></a-form-item></a-col>
        <a-col :span="8"><a-form-item label="灰度最低版本"><a-input v-model:value="form.gradual_release_min_version" /></a-form-item></a-col>
      </a-row>
      <a-form-item label="启用"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { createVersionConfig, disableVersionConfig, fetchVersionConfigs, updateVersionConfig, type AppVersionConfig } from '../api/modules/version';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';

const auth = useAuthStore();
const loading = ref(false);
const saving = ref(false);
const modalOpen = ref(false);
const isCreate = ref(false);
const rows = ref<AppVersionConfig[]>([]);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, platform: '', channel: '', bundle_id: '' });
const form = reactive<Record<string, any>>({});

const canCreate = computed(() => auth.hasPermission('button:version:config:create'));
const canUpdate = computed(() => auth.hasPermission('button:version:config:update'));
const platformOptions = [{ value: 'iOS', label: 'iOS' }, { value: 'Android', label: 'Android' }];
const channelOptions = [{ value: 'production', label: 'production' }, { value: 'testflight', label: 'testflight' }, { value: 'internal', label: 'internal' }];

function versionText(version: string, build: string) {
  if (!version) return '';
  return build ? `${version} (${build})` : version;
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchVersionConfigs(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    platform: 'iOS',
    bundle_id: '',
    channel: 'production',
    latest_version: '',
    latest_build: '',
    force_update_min_version: '',
    force_update_min_build: '',
    update_title: '发现新版本',
    update_message: '',
    release_notes: '',
    download_url: '',
    enable_gradual_release: false,
    gradual_release_percentage: 100,
    gradual_release_min_version: '',
    is_active: true,
  });
  modalOpen.value = true;
}

function openEdit(row: AppVersionConfig) {
  isCreate.value = false;
  Object.assign(form, row);
  modalOpen.value = true;
}

async function submit() {
  saving.value = true;
  try {
    if (isCreate.value) {
      await createVersionConfig(form);
      message.success('已新增版本配置');
    } else {
      await updateVersionConfig(Number(form.id), form);
      message.success('已更新版本配置');
    }
    modalOpen.value = false;
    await load();
  } catch (error: any) {
    message.error(error?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

function onDisable(id: number) {
  Modal.confirm({
    title: '停用版本配置',
    content: '停用后客户端不会再命中该配置。',
    onOk: async () => {
      await disableVersionConfig(id);
      message.success('已停用');
      await load();
    },
  });
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
