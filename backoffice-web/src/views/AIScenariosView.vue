<template>
  <a-space style="margin-bottom: 16px">
    <a-button
      v-if="canCreateScenario"
      type="primary"
      :disabled="scenarioCreateOptions.length === 0"
      @click="openCreate"
    >
      新增场景
    </a-button>
  </a-space>

  <a-table :data-source="scenarios" row-key="id" :pagination="false">
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
    <a-table-column title="激活" key="is_active">
      <template #default="{ record }">{{ record.is_active ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="操作">
      <template #default="{ record }">
        <a-button v-if="canUpdateScenario" size="small" @click="openEdit(record)">编辑</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="modalOpen" :title="isCreate ? '新增场景' : '编辑场景'" @ok="submit" :confirm-loading="saving">
    <a-form layout="vertical">
      <template v-if="isCreate">
        <a-form-item label="场景" extra="每种场景全局唯一配置一条。">
          <a-select
            v-model:value="form.scenario"
            :options="scenarioCreateOptions"
            placeholder="请选择场景"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="form.identity" :options="identityOptions" style="width: 100%" />
        </a-form-item>
        <a-form-item
          label="模型厂商（可选）"
          extra="仅列出已激活且启用中的 API 供应商；选择后将筛选可选模型（须与模型所属厂商代码一致）。接口地址由系统根据模型与厂商自动解析，无需填写。"
        >
          <a-select
            v-model:value="selectedProviderId"
            allow-clear
            show-search
            :filter-option="filterVendorOption"
            placeholder="选择已启用的模型厂商（可选）"
            :options="vendorSelectOptions"
            style="width: 100%"
            @change="onVendorChange"
          />
        </a-form-item>
        <a-form-item label="模型" extra="从模型目录中选择。">
          <a-select
            v-model:value="form.model"
            show-search
            :filter-option="filterModelOption"
            placeholder="请选择模型"
            :options="modelSelectOptions"
            style="width: 100%"
          />
        </a-form-item>
      </template>
      <template v-else>
        <a-form-item label="场景">
          <a-input :value="scenarioLabel(String(form.scenario || ''))" disabled />
        </a-form-item>
        <a-form-item label="类型">
          <a-select v-model:value="form.identity" :options="identityOptions" style="width: 100%" />
        </a-form-item>
        <a-form-item
          label="模型厂商（可选）"
          extra="用于筛选下方可选模型；接口地址仍由后端根据模型所属厂商自动解析。"
        >
          <a-select
            v-model:value="selectedProviderId"
            allow-clear
            show-search
            :filter-option="filterVendorOption"
            placeholder="选择已启用的模型厂商（可选）"
            :options="vendorSelectOptions"
            style="width: 100%"
            @change="onVendorChangeEdit"
          />
        </a-form-item>
        <a-form-item label="模型">
          <a-select
            v-model:value="form.model"
            show-search
            :filter-option="filterModelOption"
            placeholder="请选择模型"
            :options="modelSelectOptionsEdit"
            style="width: 100%"
          />
        </a-form-item>
      </template>
      <a-form-item label="温度">
        <a-input-number v-model:value="form.temperature" :step="0.1" style="width: 100%" />
      </a-form-item>
      <a-form-item label="最大 Token 数">
        <a-input-number v-model:value="form.max_tokens" :step="1" style="width: 100%" />
      </a-form-item>
      <a-form-item label="激活"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  createAIScenario,
  fetchAIModelCatalog,
  fetchAIProviders,
  fetchAIScenarios,
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
const selectedProviderId = ref<number | undefined>(undefined);
const modalOpen = ref(false);
const saving = ref(false);
const isCreate = ref(false);

const form = reactive<Partial<AIScenario>>({});

const canCreateScenario = computed(() => auth.hasPermission('button:ai:scenario:create'));
const canUpdateScenario = computed(() => auth.hasPermission('button:ai:scenario:update'));

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

const ALL_SCENARIO_KEYS = [
  { value: 'chat', label: '对话（chat）' },
  { value: 'optimization_text', label: '文本优化模型（optimization_text）' },
  { value: 'optimization_visual', label: '视觉优化模型（optimization_visual）' },
  { value: 'context_folding', label: '上下文折叠（context_folding）' },
  { value: 'router', label: 'Router 模型（router）' },
  { value: 'model_config', label: '模型配置（model_config）' },
  { value: 'report_interpretation', label: '报告解读模型（report_interpretation）' },
];

const scenarioCreateOptions = computed(() => {
  const used = new Set(scenarios.value.map((s) => s.scenario));
  return ALL_SCENARIO_KEYS.filter((o) => !used.has(o.value));
});

const enabledModelVendors = computed(() =>
  providers.value.filter((p) => p.kind === 'api' && p.is_active && p.is_using),
);

const vendorSelectOptions = computed((): { value: number; label: string; disabled?: boolean }[] => {
  const base: { value: number; label: string; disabled?: boolean }[] = enabledModelVendors.value.map((p) => ({
    value: p.id,
    label: `${p.name}（${p.company}）`,
  }));
  const id = selectedProviderId.value;
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

function filterVendorOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

function filterModelOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

function syncVendorFromRecord(record: AIScenario) {
  const company = record.provider_company;
  if (!company) {
    selectedProviderId.value = undefined;
    return;
  }
  const pname = record.provider_name;
  let hit = providers.value.find(
    (p) => p.kind === 'api' && p.company === company && (!pname || p.name === pname),
  );
  if (!hit) {
    hit = providers.value.find((p) => p.kind === 'api' && p.company === company && p.is_active && p.is_using);
  }
  selectedProviderId.value = hit?.id;
}

function onVendorChange(providerId: number | undefined) {
  if (providerId == null) {
    return;
  }
  const p = providers.value.find((x) => x.id === providerId);
  if (!p) {
    return;
  }
  const m = form.model;
  if (m) {
    const cat = catalogRows.value.find((c) => c.name === m);
    if (cat && cat.company !== p.company) {
      form.model = '';
    }
  }
}

function onVendorChangeEdit(providerId: number | undefined) {
  onVendorChange(providerId);
}

const modelSelectOptions = computed(() => {
  let list = catalogRows.value.filter((c) => c.is_active);
  if (selectedProviderId.value != null) {
    const p = providers.value.find((x) => x.id === selectedProviderId.value);
    if (p) {
      list = list.filter((c) => c.company === p.company);
    }
  }
  return list.map((c) => ({
    value: c.name,
    label: `${c.display_name}（${c.name}）`,
  }));
});

const modelSelectOptionsEdit = computed(() => {
  let list = catalogRows.value.filter((c) => c.is_active);
  if (selectedProviderId.value != null) {
    const p = providers.value.find((x) => x.id === selectedProviderId.value);
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
    fetchAIProviders('api'),
    fetchAIModelCatalog(),
  ]);
  scenarios.value = scList;
  providers.value = pvList;
  catalogRows.value = catList;
}

function openCreate() {
  const opts = scenarioCreateOptions.value;
  if (opts.length === 0) {
    message.warning('已存在全部内置场景，无法继续新增');
    return;
  }
  isCreate.value = true;
  selectedProviderId.value = undefined;
  Object.assign(form, {
    id: undefined,
    scenario: opts[0].value,
    identity: 'model',
    model: undefined,
    temperature: 0.2,
    max_tokens: 2048,
    is_active: true,
  });
  modalOpen.value = true;
}

function openEdit(row: AIScenario) {
  isCreate.value = false;
  Object.assign(form, { ...row, identity: row.identity || 'model' });
  syncVendorFromRecord(row);
  modalOpen.value = true;
}

async function submit() {
  try {
    saving.value = true;
    if (!form.model) {
      message.warning('请选择模型');
      return;
    }
    if (isCreate.value) {
      await createAIScenario({
        scenario: form.scenario,
        identity: form.identity,
        model: form.model,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        is_active: form.is_active,
      });
      message.success('场景已新增');
    } else {
      await updateAIScenario(Number(form.id), {
        identity: form.identity,
        model: form.model,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        is_active: form.is_active,
      });
      message.success('场景已更新');
    }
    modalOpen.value = false;
    await load();
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '操作失败');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
