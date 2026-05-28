<template>
  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreate" type="primary" @click="openCreate">新增小任务</a-button>
  </a-space>

  <a-table :data-source="rows" row-key="id" :pagination="false" size="small">
    <a-table-column title="编码" data-index="code" :width="120" />
    <a-table-column title="名称" data-index="name" :width="160" />
    <a-table-column title="来源" data-index="source" :width="90" />
    <a-table-column title="简介" data-index="brief" :ellipsis="true" />
    <a-table-column title="工具" key="tools" :width="180">
      <template #default="{ record }">{{ (record.tool_list || []).join(', ') || '—' }}</template>
    </a-table-column>
    <a-table-column title="操作" key="op" :width="actionsColWidth">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button v-if="canUpdate" size="small" @click="openEdit(record)">编辑</a-button>
          <a-button v-if="canUpdate" size="small" danger @click="confirmDelete(record)">删除</a-button>
        </TableHoverActions>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="modalOpen" :title="isCreate ? '新增小任务' : '编辑小任务'" @ok="submit" :confirm-loading="saving" width="640px">
    <a-form layout="vertical">
      <a-form-item label="名称"><a-input v-model:value="form.name" allow-clear /></a-form-item>
      <a-form-item label="唯一编码" extra="留空时后端按 Service_id 自动生成">
        <a-input v-model:value="form.code" allow-clear placeholder="Service_1" />
      </a-form-item>
      <a-form-item label="来源">
        <a-select v-model:value="form.source" :options="sourceOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item label="图标"><a-input v-model:value="form.icon" allow-clear placeholder="sparkles" /></a-form-item>
      <a-form-item label="简介"><a-textarea v-model:value="form.brief" :rows="2" allow-clear /></a-form-item>
      <a-form-item label="Prompt"><a-textarea v-model:value="form.prompt" :rows="5" allow-clear /></a-form-item>
      <a-form-item label="追加当前日期">
        <a-switch
          :checked="containsCurrentDateKeyword(String(form.prompt ?? ''))"
          @update:checked="
            (checked: boolean) => {
              form.prompt = setCurrentDateKeyword(String(form.prompt ?? ''), checked);
            }
          "
        />
      </a-form-item>
      <a-form-item label="工具列表">
        <a-select
          v-model:value="form.tool_list"
          mode="multiple"
          allow-clear
          show-search
          :options="toolOptions"
          style="width: 100%"
        />
        <a-space size="small" style="margin-top: 8px">
          <a-button size="small" type="link" @click="selectAllTools">全选</a-button>
          <a-button size="small" type="link" @click="clearTools">清空</a-button>
        </a-space>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { Modal, message } from 'ant-design-vue';
import {
  createSmallTask,
  deleteSmallTask,
  fetchAIToolOptions,
  fetchSmallTasks,
  updateSmallTask,
  type AIToolOption,
  type SmallTask,
} from '../api/modules/ai';
import { AI_PROMPT_KEYWORDS } from '../constants/aiPromptKeywords';
import { useAuthStore } from '../stores/auth';
import TableHoverActions from '../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const auth = useAuthStore();
const rows = ref<SmallTask[]>([]);
const modalOpen = ref(false);
const saving = ref(false);
const isCreate = ref(false);
const form = reactive<Record<string, unknown>>({});
const toolOptions = ref<AIToolOption[]>([]);

const canCreate = computed(() => auth.hasPermission('button:ai:small_task:create'));
const canUpdate = computed(() => auth.hasPermission('button:ai:small_task:update'));
const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: canUpdate.value ? 2 : 0,
    min: 60,
  }),
);

const sourceOptions = [
  { value: 'Service', label: '服务任务' },
  { value: 'Local', label: '本地任务' },
];
function normalizeStringArray(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((x) => String(x).trim()).filter(Boolean);
}

function containsCurrentDateKeyword(prompt: string): boolean {
  return prompt.includes(AI_PROMPT_KEYWORDS.currentDate);
}

function setCurrentDateKeyword(prompt: string, enabled: boolean): string {
  const lines = prompt
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== AI_PROMPT_KEYWORDS.currentDate);
  if (enabled) {
    lines.push(AI_PROMPT_KEYWORDS.currentDate);
  }
  return lines.join('\n');
}

function selectAllTools() {
  form.tool_list = toolOptions.value.map((item) => item.value);
}

function clearTools() {
  form.tool_list = [];
}

async function load() {
  const [tasks, tools] = await Promise.all([fetchSmallTasks(), fetchAIToolOptions()]);
  rows.value = tasks;
  toolOptions.value = tools;
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    id: undefined,
    name: '',
    code: '',
    source: 'Service',
    brief: '',
    prompt: '',
    icon: '',
    tool_list: [],
  });
  modalOpen.value = true;
}

function openEdit(row: SmallTask) {
  isCreate.value = false;
  Object.assign(form, {
    id: row.id,
    name: row.name,
    code: row.code,
    source: row.source,
    brief: row.brief,
    prompt: row.prompt,
    icon: row.icon,
    tool_list: row.tool_list ?? [],
  });
  modalOpen.value = true;
}

function confirmDelete(row: SmallTask) {
  Modal.confirm({
    title: '删除该小任务？',
    onOk: async () => {
      await deleteSmallTask(row.id);
      message.success('已删除');
      await load();
    },
  });
}

async function submit() {
  const tools = normalizeStringArray(form.tool_list);
  const name = String(form.name ?? '').trim();
  const prompt = String(form.prompt ?? '').trim();
  if (!name || !prompt) {
    message.warning('请填写名称和 Prompt');
    return;
  }
  const payload = {
    name,
    code: String(form.code ?? '').trim(),
    source: form.source,
    brief: form.brief,
    prompt,
    icon: form.icon,
    tool_list: tools,
  };
  try {
    saving.value = true;
    if (isCreate.value) {
      await createSmallTask(payload);
      message.success('已新增小任务');
    } else {
      await updateSmallTask(Number(form.id), payload);
      message.success('已更新小任务');
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
