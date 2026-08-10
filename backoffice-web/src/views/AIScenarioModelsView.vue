<template>
  <a-space style="margin-bottom: 16px">
    <a-button @click="router.push({ name: 'AIScenarios' })">返回场景列表</a-button>
    <a-typography-title :level="4" style="margin: 0">{{ scenarioLabel(scenarioKey) }}（{{ scenarioKey }}）</a-typography-title>
  </a-space>

  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreate" type="primary" @click="openCreate">添加模型</a-button>
  </a-space>

  <a-table :data-source="bindings" row-key="id" :pagination="false" :loading="loading">
    <a-table-column title="显示名称" key="display_name">
      <template #default="{ record }">{{ displayNameForBinding(record) }}</template>
    </a-table-column>
    <a-table-column title="基座模型" data-index="model" />
    <a-table-column title="智能体名" key="agent_name">
      <template #default="{ record }">
        {{ record.identity === 'agent' ? agentBootstrapName(record) : '—' }}
      </template>
    </a-table-column>
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
      <a-form-item label="显示名称" extra="可选；不填写时使用原模型显示名称">
        <a-input
          v-model:value="form.display_name"
          allow-clear
          :placeholder="displayNamePlaceholder"
        />
      </a-form-item>
      <a-form-item
        label="基座模型"
        extra="从模型目录选择（须已激活且厂商已配置 API）；智能体可重复选择同一基座模型；修改后智能体对外名与 baseModelName 会随之更新"
      >
        <a-select
          v-model:value="form.model"
          show-search
          :filter-option="filterModelOption"
          placeholder="选择模型"
          :options="modelSelectOptions"
          style="width: 100%"
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
      <a-form-item label="系统说明（systemProvision）" extra="下发到客户端；若试用策略行有配置则策略优先">
        <a-textarea v-model:value="form.system_provision" :rows="3" allow-clear placeholder="可选" />
      </a-form-item>
      <a-form-item label="在提示词中追加当前日期">
        <a-switch
          :checked="
            AIPromptKeywords.contains(
              AIPromptKeywords.currentDate,
              String(form.system_provision ?? ''),
            )
          "
          @update:checked="
            (checked: boolean) => {
              form.system_provision = AIPromptKeywords.setting(
                AIPromptKeywords.currentDate,
                checked,
                String(form.system_provision ?? ''),
              );
            }
          "
        />
      </a-form-item>
      <a-form-item label="简介（briefDescription）" extra="下发到客户端；若试用策略行有配置则策略优先">
        <a-textarea v-model:value="form.brief_description" :rows="2" allow-clear placeholder="可选" />
      </a-form-item>
      <a-form-item label="工具场景（aiToolScenarios）">
        <a-select
          v-model:value="form.ai_tool_scenarios"
          mode="multiple"
          allow-clear
          show-search
          :options="toolOptions"
          style="width: 100%"
        />
        <a-space size="small" style="margin-top: 8px">
          <a-button size="small" type="link" @click="selectAllToolScenarios">全选</a-button>
          <a-button size="small" type="link" @click="clearToolScenarios">清空</a-button>
        </a-space>
      </a-form-item>
      <a-form-item label="关联小任务">
        <a-select
          v-model:value="form.related_task_codes"
          mode="multiple"
          allow-clear
          show-search
          :options="smallTaskOptions"
          style="width: 100%"
        />
        <a-space size="small" style="margin-top: 8px">
          <a-button size="small" type="link" @click="selectAllRelatedTaskCodes">全选</a-button>
          <a-button size="small" type="link" @click="clearRelatedTaskCodes">清空</a-button>
        </a-space>
      </a-form-item>
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
  derivedAgentBootstrapName,
  fetchAIToolOptions,
  fetchAIModelCatalog,
  fetchSmallTasks,
  fetchScenarioBindings,
  updateScenarioBinding,
  type AIToolOption,
  type AIScenarioModelBinding,
  type AIModelCatalog,
  type SmallTask,
} from '../api/modules/ai';
import { AIPromptKeywords } from '../constants/aiPromptKeywords';
import { useAuthStore } from '../stores/auth';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const scenarioKey = computed(() => String(route.params.scenarioKey || ''));

const bindings = ref<AIScenarioModelBinding[]>([]);
const catalogRows = ref<AIModelCatalog[]>([]);
const smallTasks = ref<SmallTask[]>([]);
const toolOptions = ref<AIToolOption[]>([]);
const loading = ref(false);
const saving = ref(false);
const modalOpen = ref(false);
const isCreate = ref(false);

const form = reactive<Record<string, unknown>>({});

function normalizeStringArray(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((x) => String(x).trim()).filter((x) => x.length > 0);
}

const canCreate = computed(() => auth.hasPermission('button:ai:scenario:create'));
const canUpdate = computed(() => auth.hasPermission('button:ai:scenario:update'));

const identityOptions = [
  { value: 'model', label: '模型' },
  { value: 'agent', label: '智能体' },
];

function agentBootstrapName(row: AIScenarioModelBinding) {
  if (row.bootstrap_name) {
    return row.bootstrap_name;
  }
  if (row.model_id == null) {
    return row.model;
  }
  return derivedAgentBootstrapName(row);
}

function modelDisplayName(modelName: string) {
  const catalog = catalogRows.value.find((row) => row.name === modelName);
  return catalog?.display_name || modelName;
}

function displayNameForBinding(row: AIScenarioModelBinding) {
  const configured = String(row.display_name ?? '').trim();
  return configured || modelDisplayName(row.model);
}

function scenarioLabel(key: string) {
  const map: Record<string, string> = {
    chat: '对话',
    embedding: '向量模型',
    voice: '语音模型',
    medical_structured_extraction: '医疗文档结构化抽取',
    medical_document_type_recognition: '医疗文档类型识别',
    medical_case_extraction: '病例结构化抽取',
    health_exam_extraction: '体检报告结构化抽取',
    medical_report_extraction: '医疗报告结构化抽取',
    prescription_extraction: '处方结构化抽取',
    medication_extraction: '用药结构化抽取',
    medicine_box_extraction: '药品结构化抽取',
    optimization_text: '文本优化模型',
    optimization_visual: '视觉优化模型',
    context_folding: '上下文折叠',
    router: 'Router 模型',
    model_config: '模型配置',
    report_interpretation: '报告解读模型',
  };
  return map[key] || key;
}

const modelSelectOptions = computed(() => {
  const currentModel = typeof form.model === 'string' ? form.model : '';
  const options = catalogRows.value
    .filter((c) => c.is_active || c.name === currentModel)
    .map((c) => ({
      value: c.name,
      label: c.is_active ? `${c.display_name}（${c.name}）` : `${c.display_name}（${c.name}·已停用）`,
    }));
  if (currentModel && !options.some((item) => item.value === currentModel)) {
    options.unshift({
      value: currentModel,
      label: `${currentModel}（当前·目录中不可用）`,
    });
  }
  return options;
});

const displayNamePlaceholder = computed(() => {
  const modelName = typeof form.model === 'string' ? form.model : undefined;
  if (!modelName) {
    return '例如：报告解读助手';
  }
  return `不填写时使用：${modelDisplayName(modelName)}`;
});

const smallTaskOptions = computed(() =>
  smallTasks.value.map((task) => ({
    value: task.code,
    label: `${task.name}（${task.code}）`,
  })),
);

function filterModelOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

function selectAllToolScenarios() {
  form.ai_tool_scenarios = toolOptions.value.map((item) => item.value);
}

function clearToolScenarios() {
  form.ai_tool_scenarios = [];
}

function selectAllRelatedTaskCodes() {
  form.related_task_codes = smallTaskOptions.value.map((item) => item.value);
}

function clearRelatedTaskCodes() {
  form.related_task_codes = [];
}

async function load() {
  if (!scenarioKey.value) {
    return;
  }
  loading.value = true;
  try {
    const [b, cat, tasks, tools] = await Promise.all([
      fetchScenarioBindings(scenarioKey.value),
      fetchAIModelCatalog(),
      fetchSmallTasks(),
      fetchAIToolOptions(),
    ]);
    bindings.value = b;
    catalogRows.value = cat;
    smallTasks.value = tasks;
    toolOptions.value = tools;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    id: undefined,
    model: undefined,
    display_name: '',
    identity: 'model',
    is_default: false,
    temperature: 0.2,
    max_tokens: 2048,
    position: (bindings.value.map((x) => x.position).reduce((a, b) => Math.max(a, b), 0) || 0) + 1,
    is_active: true,
    system_provision: '',
    brief_description: '',
    ai_tool_scenarios: [],
    related_task_codes: [],
  });
  modalOpen.value = true;
}

function openEdit(row: AIScenarioModelBinding) {
  isCreate.value = false;
  Object.assign(form, {
    id: row.id,
    model: row.model,
    display_name: row.display_name ?? '',
    identity: row.identity || 'model',
    is_default: row.is_default,
    temperature: row.temperature,
    max_tokens: row.max_tokens,
    position: row.position,
    is_active: row.is_active,
    system_provision: row.system_provision ?? '',
    brief_description: row.brief_description ?? '',
    ai_tool_scenarios: row.ai_tool_scenarios ?? [],
    related_task_codes: row.related_task_codes ?? [],
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
    const displayName = String(form.display_name ?? '').trim();
    const tools = normalizeStringArray(form.ai_tool_scenarios);
    if (isCreate.value) {
      await createScenarioBinding(scenarioKey.value, {
        model: form.model,
        display_name: displayName,
        identity: form.identity,
        is_default: form.is_default,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        position: form.position,
        is_active: form.is_active,
        system_provision: form.system_provision,
        brief_description: form.brief_description,
        ai_tool_scenarios: tools,
        related_task_codes: form.related_task_codes,
      });
      message.success('已添加');
    } else {
      await updateScenarioBinding(Number(form.id), {
        model: form.model,
        display_name: displayName,
        identity: form.identity,
        is_default: form.is_default,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        position: form.position,
        is_active: form.is_active,
        system_provision: form.system_provision,
        brief_description: form.brief_description,
        ai_tool_scenarios: tools,
        related_task_codes: form.related_task_codes,
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
