<template>
  <a-space style="margin-bottom: 16px">
    <a-button @click="router.push({ name: 'AIScenarios' })">返回场景列表</a-button>
    <a-typography-title :level="4" style="margin: 0">{{ scenarioLabel(scenarioKey) }}（{{ scenarioKey }}）</a-typography-title>
  </a-space>

  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreate" type="primary" @click="openCreate">添加模型</a-button>
  </a-space>

  <a-table :data-source="bindings" row-key="id" :pagination="false" :loading="loading">
    <a-table-column title="模型" data-index="model" />
    <a-table-column title="类型" key="identity">
      <template #default="{ record }">{{ record.identity === 'agent' ? '智能体' : '模型' }}</template>
    </a-table-column>
    <a-table-column title="默认" key="is_default">
      <template #default="{ record }">{{ record.is_default ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="厂商" key="vendor" :ellipsis="true">
      <template #default="{ record }">
        {{ record.provider_name ? `${record.provider_name}（${record.provider_company || ''}）` : '—' }}
      </template>
    </a-table-column>
    <a-table-column title="温度" data-index="temperature" />
    <a-table-column title="最大 Token" data-index="max_tokens" />
    <a-table-column title="排序" data-index="position" />
    <a-table-column title="激活" key="is_active">
      <template #default="{ record }">{{ record.is_active ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="操作" key="op">
      <template #default="{ record }">
        <a-button v-if="canUpdate" size="small" type="link" @click="setDefault(record)" :disabled="record.is_default">
          设为默认
        </a-button>
        <a-button v-if="canUpdate" size="small" @click="openEdit(record)">编辑</a-button>
        <a-button v-if="canUpdate" size="small" danger @click="confirmDelete(record)">删除</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="modalOpen" :title="isCreate ? '添加模型' : '编辑模型'" @ok="submit" :confirm-loading="saving" width="520px">
    <a-form layout="vertical">
      <a-form-item label="模型" extra="从模型目录选择（须已激活且厂商已配置 API）">
        <a-select
          v-model:value="form.model"
          show-search
          :filter-option="filterModelOption"
          placeholder="选择模型"
          :options="modelSelectOptions"
          style="width: 100%"
          :disabled="!isCreate"
        />
      </a-form-item>
      <a-form-item label="类型">
        <a-select v-model:value="form.identity" :options="identityOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item label="设为默认">
        <a-switch v-model:checked="form.is_default" />
      </a-form-item>
      <a-form-item label="温度">
        <a-input-number v-model:value="form.temperature" :step="0.1" style="width: 100%" />
      </a-form-item>
      <a-form-item label="最大 Token 数">
        <a-input-number v-model:value="form.max_tokens" :step="1" style="width: 100%" />
      </a-form-item>
      <a-form-item label="排序">
        <a-input-number v-model:value="form.position" :step="1" style="width: 100%" />
      </a-form-item>
      <a-form-item label="激活"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Modal, message } from 'ant-design-vue';
import {
  createScenarioBinding,
  deleteScenarioBinding,
  fetchAIModelCatalog,
  fetchScenarioBindings,
  updateScenarioBinding,
  type AIScenarioModelBinding,
  type AIModelCatalog,
} from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const scenarioKey = computed(() => String(route.params.scenarioKey || ''));

const bindings = ref<AIScenarioModelBinding[]>([]);
const catalogRows = ref<AIModelCatalog[]>([]);
const loading = ref(false);
const saving = ref(false);
const modalOpen = ref(false);
const isCreate = ref(false);

const form = reactive<Record<string, unknown>>({});

const canCreate = computed(() => auth.hasPermission('button:ai:scenario:create'));
const canUpdate = computed(() => auth.hasPermission('button:ai:scenario:update'));

const identityOptions = [
  { value: 'model', label: '模型' },
  { value: 'agent', label: '智能体' },
];

function scenarioLabel(key: string) {
  const map: Record<string, string> = {
    chat: '对话',
    optimization_text: '文本优化模型',
    optimization_visual: '视觉优化模型',
    context_folding: '上下文折叠',
    router: 'Router 模型',
    model_config: '模型配置',
    report_interpretation: '报告解读模型',
  };
  return map[key] || key;
}

const modelSelectOptions = computed(() =>
  catalogRows.value
    .filter((c) => c.is_active)
    .map((c) => ({
      value: c.name,
      label: `${c.display_name}（${c.name}）`,
    })),
);

function filterModelOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

async function load() {
  if (!scenarioKey.value) {
    return;
  }
  loading.value = true;
  try {
    const [b, cat] = await Promise.all([fetchScenarioBindings(scenarioKey.value), fetchAIModelCatalog()]);
    bindings.value = b;
    catalogRows.value = cat;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    id: undefined,
    model: undefined,
    identity: 'model',
    is_default: false,
    temperature: 0.2,
    max_tokens: 2048,
    position: (bindings.value.map((x) => x.position).reduce((a, b) => Math.max(a, b), 0) || 0) + 1,
    is_active: true,
  });
  modalOpen.value = true;
}

function openEdit(row: AIScenarioModelBinding) {
  isCreate.value = false;
  Object.assign(form, {
    id: row.id,
    model: row.model,
    identity: row.identity || 'model',
    is_default: row.is_default,
    temperature: row.temperature,
    max_tokens: row.max_tokens,
    position: row.position,
    is_active: row.is_active,
  });
  modalOpen.value = true;
}

async function setDefault(row: AIScenarioModelBinding) {
  try {
    saving.value = true;
    await updateScenarioBinding(row.id, { is_default: true });
    message.success('已设为默认模型');
    await load();
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '操作失败');
  } finally {
    saving.value = false;
  }
}

function confirmDelete(row: AIScenarioModelBinding) {
  Modal.confirm({
    title: '删除该模型绑定？',
    onOk: async () => {
      try {
        await deleteScenarioBinding(row.id);
        message.success('已删除');
        await load();
      } catch (e: unknown) {
        message.error(e instanceof Error ? e.message : '删除失败');
      }
    },
  });
}

async function submit() {
  try {
    saving.value = true;
    if (!form.model) {
      message.warning('请选择模型');
      return;
    }
    if (isCreate.value) {
      await createScenarioBinding(scenarioKey.value, {
        model: form.model,
        identity: form.identity,
        is_default: form.is_default,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        position: form.position,
        is_active: form.is_active,
      });
      message.success('已添加');
    } else {
      await updateScenarioBinding(Number(form.id), {
        identity: form.identity,
        is_default: form.is_default,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        position: form.position,
        is_active: form.is_active,
      });
      message.success('已更新');
    }
    modalOpen.value = false;
    await load();
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : '操作失败');
  } finally {
    saving.value = false;
  }
}

watch(
  () => route.params.scenarioKey,
  () => {
    load();
  },
);

onMounted(load);
</script>
