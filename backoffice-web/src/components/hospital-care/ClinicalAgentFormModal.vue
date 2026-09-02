<template>
  <a-modal
    :open="open"
    :title="agentId ? '维护智能体' : '新建智能体'"
    :confirm-loading="saving"
    width="760px"
    destroy-on-close
    @ok="submit"
    @cancel="$emit('update:open', false)"
  >
    <a-spin :spinning="loading">
      <a-alert v-if="errorText" type="error" show-icon :message="errorText" style="margin-bottom: 16px" />
      <a-form layout="vertical">
        <a-typography-title :level="5">归属</a-typography-title>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="医生" required>
              <a-select
                v-model:value="form.doctor_id"
                :disabled="Boolean(agentId)"
                show-search
                option-filter-prop="label"
                placeholder="选择医生"
                :options="doctorOptions"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="科室" required>
              <a-select v-model:value="form.department_id" show-search option-filter-prop="label" placeholder="选择科室" :options="departmentOptions" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-typography-title :level="5">患者侧展示</a-typography-title>
        <a-form-item label="名称" required>
          <a-input v-model:value="form.name" />
        </a-form-item>
        <a-form-item label="简介">
          <a-textarea v-model:value="form.public_summary" :rows="2" />
        </a-form-item>
        <a-form-item label="问候语">
          <a-textarea v-model:value="form.greeting" :rows="2" />
        </a-form-item>
        <a-form-item label="服务边界" required>
          <a-textarea v-model:value="form.service_boundary" :rows="3" placeholder="例如：健康信息与就医指导，不提供确诊。" />
        </a-form-item>

        <a-typography-title :level="5">AI 运行配置</a-typography-title>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="基座模型" required>
              <a-select v-model:value="form.binding.model" show-search option-filter-prop="label" placeholder="选择模型" :options="modelOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="温度">
              <a-input-number v-model:value="form.binding.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="6">
            <a-form-item label="最大 Token">
              <a-input-number v-model:value="form.binding.max_tokens" :min="64" :max="8192" :step="64" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="系统指令">
          <a-textarea v-model:value="form.binding.system_provision" :rows="4" />
        </a-form-item>
        <a-form-item label="内部简介">
          <a-textarea v-model:value="form.binding.brief_description" :rows="2" />
        </a-form-item>
        <a-form-item label="客户端工具">
          <a-select v-model:value="form.binding.ai_tool_scenarios" mode="multiple" allow-clear :options="options.ai_tool_scenarios" placeholder="可选" />
        </a-form-item>
        <a-form-item label="服务端工具">
          <a-select
            v-model:value="form.binding.server_tool_scenarios"
            mode="multiple"
            allow-clear
            :options="options.server_tool_scenarios"
            placeholder="可选"
          />
        </a-form-item>

        <a-typography-title :level="5">关联知识库</a-typography-title>
        <a-form-item>
          <a-select
            v-model:value="selectedKnowledgeIds"
            mode="multiple"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="选择知识库，可多选后调整顺序"
            :options="knowledgeOptions"
            @change="onKnowledgeChange"
          />
        </a-form-item>
        <div v-if="form.knowledge_bases.length" class="knowledge-order">
          <div v-for="(item, index) in form.knowledge_bases" :key="item.profile_id" class="knowledge-order-row">
            <span>{{ knowledgeName(item.profile_id) }}</span>
            <a-space>
              <a-button size="small" :disabled="index === 0" @click="moveKnowledge(index, -1)">上移</a-button>
              <a-button size="small" :disabled="index === form.knowledge_bases.length - 1" @click="moveKnowledge(index, 1)">下移</a-button>
            </a-space>
          </div>
        </div>

        <a-descriptions v-if="detail" bordered size="small" :column="2" style="margin-top: 16px">
          <a-descriptions-item label="智能体 ID">{{ detail.id }}</a-descriptions-item>
          <a-descriptions-item label="场景绑定 ID">{{ detail.scenario_binding_id || '--' }}</a-descriptions-item>
          <a-descriptions-item label="审核状态">{{ detail.publication_status }}</a-descriptions-item>
          <a-descriptions-item label="发布时间">{{ detail.published_at || '--' }}</a-descriptions-item>
        </a-descriptions>
      </a-form>
    </a-spin>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { message } from 'ant-design-vue';
import {
  createAgent,
  fetchAgent,
  fetchAgentFormOptions,
  hospitalCareMessage,
  updateAgent,
  type AgentFormOptions,
  type AgentRow,
} from '../../api/modules/hospitalCare';

const props = defineProps<{
  open: boolean;
  hospitalId: string;
  agentId?: string;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  saved: [];
}>();

const loading = ref(false);
const saving = ref(false);
const errorText = ref('');
const options = ref<AgentFormOptions>({
  doctors: [],
  departments: [],
  models: [],
  knowledge_bases: [],
  embedding_bindings: [],
  ai_tool_scenarios: [],
  server_tool_scenarios: [],
});
const detail = ref<AgentRow | null>(null);
const selectedKnowledgeIds = ref<string[]>([]);
const form = reactive({
  doctor_id: '',
  department_id: '',
  name: '',
  public_summary: '',
  greeting: '',
  service_boundary: '',
  knowledge_bases: [] as Array<{ profile_id: string }>,
  binding: {
    model: '',
    temperature: 0.2,
    max_tokens: 2048,
    system_provision: '',
    brief_description: '',
    ai_tool_scenarios: [] as string[],
    server_tool_scenarios: [] as string[],
  },
});

const doctorOptions = computed(() => options.value.doctors.map((item) => ({ value: item.id, label: item.display_name })));
const departmentOptions = computed(() => options.value.departments.map((item) => ({ value: item.id, label: item.name })));
const modelOptions = computed(() => options.value.models.map((item) => ({ value: item.name, label: `${item.display_name} (${item.name})` })));
const knowledgeOptions = computed(() => options.value.knowledge_bases.map((item) => ({ value: item.id, label: item.name })));

function knowledgeName(id: string) {
  return options.value.knowledge_bases.find((item) => item.id === id)?.name || id;
}

function onKnowledgeChange(ids: string[]) {
  const current = new Map(form.knowledge_bases.map((item, index) => [item.profile_id, index]));
  form.knowledge_bases = ids
    .slice()
    .sort((a, b) => (current.get(a) ?? 999) - (current.get(b) ?? 999))
    .map((profile_id) => ({ profile_id }));
}

function moveKnowledge(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= form.knowledge_bases.length) {
    return;
  }
  const copy = form.knowledge_bases.slice();
  const [row] = copy.splice(index, 1);
  copy.splice(target, 0, row);
  form.knowledge_bases = copy;
  selectedKnowledgeIds.value = copy.map((item) => item.profile_id);
}

function resetForm() {
  form.doctor_id = '';
  form.department_id = '';
  form.name = '';
  form.public_summary = '';
  form.greeting = '';
  form.service_boundary = '';
  form.knowledge_bases = [];
  selectedKnowledgeIds.value = [];
  form.binding.model = '';
  form.binding.temperature = 0.2;
  form.binding.max_tokens = 2048;
  form.binding.system_provision = '';
  form.binding.brief_description = '';
  form.binding.ai_tool_scenarios = [];
  form.binding.server_tool_scenarios = [];
  detail.value = null;
}

async function load() {
  if (!props.open || !props.hospitalId) {
    return;
  }
  loading.value = true;
  errorText.value = '';
  try {
    options.value = await fetchAgentFormOptions(props.hospitalId);
    if (!props.agentId) {
      resetForm();
      if (options.value.models[0]) {
        form.binding.model = options.value.models[0].name;
      }
      return;
    }
    const agent = await fetchAgent(props.agentId);
    detail.value = agent;
    form.doctor_id = agent.doctor.id;
    form.department_id = agent.department?.id || '';
    form.name = agent.name;
    form.public_summary = agent.public_summary;
    form.greeting = agent.greeting;
    form.service_boundary = agent.service_boundary;
    form.knowledge_bases = (agent.knowledge_bindings || [])
      .filter((item) => item.profile_id)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((item) => ({ profile_id: item.profile_id as string }));
    selectedKnowledgeIds.value = form.knowledge_bases.map((item) => item.profile_id);
    form.binding.model = agent.binding?.model || '';
    form.binding.temperature = agent.binding?.temperature ?? 0.2;
    form.binding.max_tokens = agent.binding?.max_tokens ?? 2048;
    form.binding.system_provision = agent.binding?.system_provision || '';
    form.binding.brief_description = agent.binding?.brief_description || '';
    form.binding.ai_tool_scenarios = agent.binding?.ai_tool_scenarios || [];
    form.binding.server_tool_scenarios = agent.binding?.server_tool_scenarios || [];
  } catch (error) {
    errorText.value = hospitalCareMessage(error);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!form.doctor_id || !form.department_id || !form.name.trim() || !form.binding.model) {
    message.error('请填写医生、科室、名称和基座模型');
    return;
  }
  if (!form.service_boundary.trim()) {
    message.error('请填写服务边界，说明智能体可回答的范围');
    return;
  }
  saving.value = true;
  try {
    const knowledge_bases = form.knowledge_bases.map((item) => ({ profile_id: item.profile_id }));
    if (props.agentId && detail.value) {
      await updateAgent(props.agentId, {
        version: detail.value.version || 1,
        department_id: form.department_id,
        name: form.name.trim(),
        public_summary: form.public_summary,
        greeting: form.greeting,
        service_boundary: form.service_boundary,
        knowledge_bases,
        binding: {
          ...form.binding,
          updated_at: detail.value.binding?.updated_at || undefined,
        },
      });
      message.success('已保存智能体');
    } else {
      await createAgent(props.hospitalId, {
        doctor_id: form.doctor_id,
        department_id: form.department_id,
        name: form.name.trim(),
        public_summary: form.public_summary,
        greeting: form.greeting,
        service_boundary: form.service_boundary,
        knowledge_bases,
        binding: form.binding,
      });
      message.success('已创建智能体');
    }
    emit('update:open', false);
    emit('saved');
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    saving.value = false;
  }
}

watch(
  () => [props.open, props.hospitalId, props.agentId],
  () => {
    if (props.open) {
      load();
    }
  },
);
</script>

<style scoped>
.knowledge-order {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: -8px;
}
.knowledge-order-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
</style>
