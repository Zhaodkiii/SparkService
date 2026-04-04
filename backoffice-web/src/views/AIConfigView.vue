<template>
  <a-typography-title :level="4">AI 场景配置</a-typography-title>
  <a-table :data-source="scenarios" row-key="id" :pagination="false" style="margin-bottom: 24px">
    <a-table-column title="场景" key="scenario">
      <template #default="{ record }">{{ scenarioLabel(record.scenario) }}</template>
    </a-table-column>
    <a-table-column title="类型" key="identity">
      <template #default="{ record }">{{ record.identity === 'agent' ? '智能体' : '模型' }}</template>
    </a-table-column>
    <a-table-column title="模型" data-index="model" />
    <a-table-column title="厂商" key="vendor" :ellipsis="true">
      <template #default="{ record }">
        {{ record.provider_name ? `${record.provider_name}（${record.provider_company || ''}）` : '—' }}
      </template>
    </a-table-column>
    <a-table-column title="温度" data-index="temperature" />
    <a-table-column title="最大 Token 数" data-index="max_tokens" />
    <a-table-column title="操作">
      <template #default="{ record }">
        <a-button v-if="canUpdateScenario" size="small" @click="openScenarioModal(record)">编辑</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-typography-title :level="4">Provider 配置</a-typography-title>
  <a-table :data-source="providers" row-key="id" :pagination="false">
    <a-table-column title="类型" data-index="kind" />
    <a-table-column title="名称" data-index="name" />
    <a-table-column title="公司" data-index="company" />
    <a-table-column title="URL" data-index="request_url" />
    <a-table-column title="启用" key="is_using">
      <template #default="{ record }">{{ record.is_using ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="操作">
      <template #default="{ record }">
        <a-button v-if="canUpdateProvider" size="small" @click="openProviderModal(record)">编辑</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="scenarioModalOpen" title="编辑场景" @ok="submitScenario" :confirm-loading="saving">
    <a-form layout="vertical">
      <a-form-item label="场景">
        <a-input :value="scenarioLabel(String(scenarioForm.scenario || ''))" disabled />
      </a-form-item>
      <a-form-item label="类型">
        <a-select v-model:value="scenarioForm.identity" :options="identityOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item
        label="模型厂商（可选）"
        extra="用于筛选可选模型；接口地址由后端根据模型所属厂商自动解析，无需填写。"
      >
        <a-select
          v-model:value="scenarioVendorId"
          allow-clear
          show-search
          :filter-option="filterScenarioVendorOption"
          placeholder="选择已启用的模型厂商（可选）"
          :options="scenarioVendorSelectOptions"
          style="width: 100%"
          @change="onScenarioVendorChange"
        />
      </a-form-item>
      <a-form-item label="模型">
        <a-select
          v-model:value="scenarioForm.model"
          show-search
          :filter-option="filterScenarioModelOption"
          placeholder="请选择模型"
          :options="scenarioModelSelectOptions"
          style="width: 100%"
        />
      </a-form-item>
      <a-form-item label="温度"><a-input-number v-model:value="scenarioForm.temperature" :step="0.1" style="width: 100%" /></a-form-item>
      <a-form-item label="最大 Token 数"><a-input-number v-model:value="scenarioForm.max_tokens" :step="1" style="width: 100%" /></a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="providerModalOpen" title="编辑 Provider" @ok="submitProvider" :confirm-loading="saving">
    <a-form layout="vertical">
      <a-form-item label="URL"><a-input v-model:value="providerForm.request_url" /></a-form-item>
      <a-form-item label="Position"><a-input-number v-model:value="providerForm.position" style="width: 100%" /></a-form-item>
      <a-form-item label="启用中"><a-switch v-model:checked="providerForm.is_using" /></a-form-item>
      <a-form-item label="激活"><a-switch v-model:checked="providerForm.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  fetchAIModelCatalog,
  fetchAIProviders,
  fetchAIScenarios,
  updateAIProvider,
  updateAIScenario,
  type AIModelCatalog,
  type AIProvider,
  type AIScenario,
} from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const scenarios = ref<AIScenario[]>([]);
const providers = ref<AIProvider[]>([]);
const catalogRows = ref<AIModelCatalog[]>([]);
const saving = ref(false);

const canUpdateScenario = computed(() => auth.hasPermission('button:ai:scenario:update'));
const canUpdateProvider = computed(() => auth.hasPermission('button:ai:provider:update'));

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

const scenarioModalOpen = ref(false);
const providerModalOpen = ref(false);
const scenarioForm = reactive<Partial<AIScenario>>({});
const providerForm = reactive<Record<string, unknown>>({});
const scenarioVendorId = ref<number | undefined>(undefined);

const enabledApiProviders = computed(() =>
  providers.value.filter((p) => p.kind === 'api' && p.is_active && p.is_using),
);

const scenarioVendorSelectOptions = computed((): { value: number; label: string; disabled?: boolean }[] => {
  const base: { value: number; label: string; disabled?: boolean }[] = enabledApiProviders.value.map((p) => ({
    value: p.id,
    label: `${p.name}（${p.company}）`,
  }));
  const id = scenarioVendorId.value;
  if (id != null && !base.some((o) => o.value === id)) {
    const p = providers.value.find((x) => x.id === id && x.kind === 'api');
    if (p) {
      base.unshift({
        value: p.id,
        label: `${p.name}（${p.company}，当前未同时满足激活+启用中）`,
        disabled: true,
      });
    }
  }
  return base;
});

function filterScenarioVendorOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

function filterScenarioModelOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

function syncScenarioVendorFromRecord(record: AIScenario) {
  const company = record.provider_company;
  if (!company) {
    scenarioVendorId.value = undefined;
    return;
  }
  const pname = record.provider_name;
  let hit = providers.value.find(
    (p) => p.kind === 'api' && p.company === company && (!pname || p.name === pname),
  );
  if (!hit) {
    hit = providers.value.find((p) => p.kind === 'api' && p.company === company && p.is_active && p.is_using);
  }
  scenarioVendorId.value = hit?.id;
}

function onScenarioVendorChange(providerId: number | undefined) {
  if (providerId == null) {
    return;
  }
  const p = providers.value.find((x) => x.id === providerId);
  if (!p) {
    return;
  }
  const m = scenarioForm.model;
  if (m) {
    const cat = catalogRows.value.find((c) => c.name === m);
    if (cat && cat.company !== p.company) {
      scenarioForm.model = undefined;
    }
  }
}

const scenarioModelSelectOptions = computed(() => {
  let list = catalogRows.value.filter((c) => c.is_active);
  if (scenarioVendorId.value != null) {
    const p = providers.value.find((x) => x.id === scenarioVendorId.value);
    if (p) {
      list = list.filter((c) => c.company === p.company);
    }
  }
  return list.map((c) => ({
    value: c.name,
    label: `${c.display_name}（${c.name}）`,
  }));
});

async function load() {
  const [scList, pvList, catList] = await Promise.all([
    fetchAIScenarios(),
    fetchAIProviders(''),
    fetchAIModelCatalog(),
  ]);
  scenarios.value = scList;
  providers.value = pvList;
  catalogRows.value = catList;
}

function openScenarioModal(row: AIScenario) {
  Object.assign(scenarioForm, {
    ...row,
    identity: row.identity || 'model',
  });
  syncScenarioVendorFromRecord(row);
  scenarioModalOpen.value = true;
}

function openProviderModal(row: AIProvider) {
  Object.assign(providerForm, row);
  providerModalOpen.value = true;
}

async function submitScenario() {
  try {
    saving.value = true;
    if (!scenarioForm.model) {
      message.warning('请选择模型');
      return;
    }
    await updateAIScenario(Number(scenarioForm.id), {
      identity: scenarioForm.identity,
      model: scenarioForm.model,
      temperature: scenarioForm.temperature,
      max_tokens: scenarioForm.max_tokens,
    });
    scenarioModalOpen.value = false;
    message.success('场景已更新');
    await load();
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '更新失败');
  } finally {
    saving.value = false;
  }
}

async function submitProvider() {
  try {
    saving.value = true;
    await updateAIProvider(Number(providerForm.id), {
      request_url: providerForm.request_url,
      position: providerForm.position,
      is_using: providerForm.is_using,
      is_active: providerForm.is_active,
    });
    providerModalOpen.value = false;
    message.success('Provider 已更新');
    await load();
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '更新失败');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
