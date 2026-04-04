<template>
  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreateProvider" type="primary" @click="openCreate">新增 AI 供应商</a-button>
  </a-space>

  <a-table :data-source="providers" row-key="id" :pagination="false">
    <a-table-column title="类型" key="kind">
      <template #default="{ record }">{{ kindLabel(record.kind) }}</template>
    </a-table-column>
    <a-table-column title="名称" data-index="name" />
    <a-table-column title="厂商代码" data-index="company" />
    <a-table-column title="API 端点" data-index="request_url" :ellipsis="true" />
    <a-table-column title="帮助链接" data-index="help" :ellipsis="true" />
    <a-table-column title="隐私政策地址" data-index="privacy_policy_url" :ellipsis="true" />
    <a-table-column title="排序" data-index="position" />
    <a-table-column title="启用中" key="is_using">
      <template #default="{ record }">{{ record.is_using ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="激活" key="is_active">
      <template #default="{ record }">{{ record.is_active ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="操作">
      <template #default="{ record }">
        <a-button v-if="canUpdateProvider" size="small" @click="openEdit(record)">编辑</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-modal
    v-model:open="modalOpen"
    :title="isCreate ? '新增 AI 供应商' : '编辑 AI 供应商'"
    @ok="submit"
    :confirm-loading="saving"
  >
    <a-form layout="vertical">
      <a-form-item label="类型">
        <a-select v-model:value="form.kind" :disabled="!isCreate" :options="kindOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item label="名称"><a-input v-model:value="form.name" :disabled="!isCreate" /></a-form-item>
      <a-form-item label="厂商代码"><a-input v-model:value="form.company" :disabled="!isCreate" /></a-form-item>
      <a-form-item label="API Key（密文）"><a-input-password v-model:value="form.key" /></a-form-item>
      <a-form-item label="API 端点"><a-input v-model:value="form.request_url" /></a-form-item>
      <a-form-item label="帮助链接"><a-input v-model:value="form.help" /></a-form-item>
      <a-form-item label="隐私政策地址"><a-input v-model:value="form.privacy_policy_url" /></a-form-item>
      <a-form-item label="排序"><a-input-number v-model:value="form.position" style="width: 100%" /></a-form-item>
      <a-form-item label="启用中"><a-switch v-model:checked="form.is_using" /></a-form-item>
      <a-form-item label="激活"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import { createAIProvider, fetchAIProviders, updateAIProvider, type AIProvider } from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const providers = ref<AIProvider[]>([]);
const modalOpen = ref(false);
const saving = ref(false);
const isCreate = ref(false);

const kindOptions = [
  { value: 'api', label: 'API' },
  { value: 'search', label: '搜索' },
  { value: 'tool', label: '工具' },
];

function kindLabel(kind: string) {
  return kindOptions.find((o) => o.value === kind)?.label ?? kind;
}

const form = reactive<Record<string, unknown>>({});

const canCreateProvider = computed(() => auth.hasPermission('button:ai:provider:create'));
const canUpdateProvider = computed(() => auth.hasPermission('button:ai:provider:update'));

async function load() {
  providers.value = await fetchAIProviders('');
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    id: undefined,
    kind: 'api',
    name: '',
    company: '',
    key: '',
    request_url: '',
    position: 0,
    is_using: false,
    is_active: true,
    is_hidden: false,
    capability_class: '',
    help: '',
    privacy_policy_url: '',
    source: 'custom',
  });
  modalOpen.value = true;
}

function openEdit(row: AIProvider) {
  isCreate.value = false;
  Object.assign(form, row, { key: '' });
  modalOpen.value = true;
}

async function submit() {
  try {
    saving.value = true;
    if (isCreate.value) {
      await createAIProvider({
        kind: form.kind,
        name: form.name,
        company: form.company,
        key: form.key,
        request_url: form.request_url,
        position: form.position,
        is_using: form.is_using,
        is_active: form.is_active,
        is_hidden: form.is_hidden,
        capability_class: form.capability_class,
        help: form.help,
        privacy_policy_url: form.privacy_policy_url,
        source: form.source,
      });
      message.success('已新增 AI 供应商');
    } else {
      const patch: Record<string, unknown> = {
        request_url: form.request_url,
        position: form.position,
        is_using: form.is_using,
        is_active: form.is_active,
        is_hidden: form.is_hidden,
        capability_class: form.capability_class,
        help: form.help,
        privacy_policy_url: form.privacy_policy_url,
      };
      if (typeof form.key === 'string' && form.key.trim() !== '') {
        patch.key = form.key;
      }
      await updateAIProvider(Number(form.id), patch);
      message.success('已更新 AI 供应商');
    }
    modalOpen.value = false;
    await load();
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : '操作失败';
    message.error(msg);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
