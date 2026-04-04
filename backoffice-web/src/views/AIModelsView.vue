<template>
  <a-space style="margin-bottom: 16px">
    <a-button v-if="canCreate" type="primary" @click="openCreate">新增模型目录</a-button>
  </a-space>

  <a-table
    :data-source="rows"
    row-key="id"
    :pagination="false"
    :scroll="{ x: 2400 }"
    size="small"
  >
    <a-table-column title="模型名称" data-index="name" :width="160" fixed="left" />
    <a-table-column title="显示名称" data-index="display_name" :width="140" />
    <a-table-column title="厂商名称" data-index="company" :width="100" />
    <a-table-column title="价格档位" key="price_tier" :width="96">
      <template #default="{ record }">{{ priceTierLabel(record.price_tier) }}</template>
    </a-table-column>
    <a-table-column title="文本" key="supports_text" :width="72">
      <template #default="{ record }">{{ record.supports_text ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="视觉" key="supports_multimodal" :width="72">
      <template #default="{ record }">{{ record.supports_multimodal ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="思考" key="supports_reasoning" :width="72">
      <template #default="{ record }">{{ record.supports_reasoning ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="思考可控" key="reasoning_controllable" :width="88">
      <template #default="{ record }">{{ record.reasoning_controllable ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="搜索" key="supports_search" :width="72">
      <template #default="{ record }">{{ record.supports_search ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="工具" key="supports_tool_use" :width="72">
      <template #default="{ record }">{{ record.supports_tool_use ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="排序" data-index="position" :width="64" />
    <a-table-column title="激活" key="is_active" :width="72">
      <template #default="{ record }">{{ record.is_active ? '是' : '否' }}</template>
    </a-table-column>
    <a-table-column title="操作" key="op" :width="88" fixed="right">
      <template #default="{ record }">
        <a-button v-if="canUpdate" size="small" @click="openEdit(record)">编辑</a-button>
      </template>
    </a-table-column>
  </a-table>

  <a-modal v-model:open="modalOpen" :title="isCreate ? '新增模型目录' : '编辑模型目录'" @ok="submit" :confirm-loading="saving" width="560px">
    <a-form layout="vertical">
      <a-form-item
        v-if="isCreate"
        label="模型名称（唯一标识）"
        extra="请手动录入 API 侧模型唯一标识（如 gpt-4o-mini）；创建后不可修改，不与现有目录或场景做关联选择。"
      >
        <a-input
          v-model:value="form.name"
          placeholder="录入模型唯一标识"
          allow-clear
          style="width: 100%"
        />
      </a-form-item>
      <a-form-item v-else label="模型名称（不可改）"><a-input v-model:value="form.name" disabled /></a-form-item>
      <a-form-item label="显示名称"><a-input v-model:value="form.display_name" /></a-form-item>
      <a-form-item
        label="厂商信息"
        extra="从已激活且启用中的 API 厂商中选择；保存为厂商代码（company），用于后端匹配请求端点。"
      >
        <a-select
          v-model:value="form.company"
          allow-clear
          show-search
          :filter-option="filterVendorCompanyOption"
          placeholder="选择已启用的模型厂商"
          :options="vendorCompanyOptions"
          style="width: 100%"
        />
      </a-form-item>
      <a-form-item label="价格" extra="0 免费，1 经济，2 标准，3 高级">
        <a-select v-model:value="form.price_tier" :options="priceTierOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item label="来源">
        <a-select v-model:value="form.source" :options="sourceOptions" style="width: 100%" />
      </a-form-item>
      <a-form-item label="排序"><a-input-number v-model:value="form.position" style="width: 100%" /></a-form-item>
      <a-form-item label="文本"><a-switch v-model:checked="form.supports_text" /></a-form-item>
      <a-form-item label="视觉"><a-switch v-model:checked="form.supports_multimodal" /></a-form-item>
      <a-form-item label="思考"><a-switch v-model:checked="form.supports_reasoning" /></a-form-item>
      <a-form-item label="思考可控"><a-switch v-model:checked="form.reasoning_controllable" /></a-form-item>
      <a-form-item label="联网搜索"><a-switch v-model:checked="form.supports_search" /></a-form-item>
      <a-form-item label="工具调用"><a-switch v-model:checked="form.supports_tool_use" /></a-form-item>
      <a-form-item label="语音生成"><a-switch v-model:checked="form.supports_voice_gen" /></a-form-item>
      <a-form-item label="图像生成"><a-switch v-model:checked="form.supports_image_gen" /></a-form-item>
      <a-form-item label="隐藏"><a-switch v-model:checked="form.is_hidden" /></a-form-item>
      <a-form-item label="激活"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message } from 'ant-design-vue';
import {
  createAIModelCatalog,
  fetchAIModelCatalog,
  fetchAIProviders,
  updateAIModelCatalog,
  type AIModelCatalog,
  type AIProvider,
} from '../api/modules/ai';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const rows = ref<AIModelCatalog[]>([]);
const providers = ref<AIProvider[]>([]);
const modalOpen = ref(false);
const saving = ref(false);
const isCreate = ref(false);

const form = reactive<Record<string, unknown>>({});

const canCreate = computed(() => auth.hasPermission('button:ai:model:create'));
const canUpdate = computed(() => auth.hasPermission('button:ai:model:update'));

const sourceOptions = [
  { value: 'system', label: '系统' },
  { value: 'custom', label: '自定义' },
];

const priceTierOptions = [
  { value: 0, label: '0 · 免费' },
  { value: 1, label: '1 · 经济' },
  { value: 2, label: '2 · 标准' },
  { value: 3, label: '3 · 高级' },
];

function priceTierLabel(tier: number | undefined) {
  const m: Record<number, string> = {
    0: '免费',
    1: '经济',
    2: '标准',
    3: '高级',
  };
  if (tier === undefined || tier === null) {
    return '—';
  }
  return m[Number(tier)] ?? String(tier);
}

const enabledApiProviders = computed(() =>
  providers.value.filter((p) => p.kind === 'api' && p.is_active && p.is_using),
);

/** 下拉 value 为厂商代码 company，与模型目录字段一致 */
const vendorCompanyOptions = computed((): { value: string; label: string; disabled?: boolean }[] => {
  const base: { value: string; label: string; disabled?: boolean }[] = enabledApiProviders.value.map((p) => ({
    value: p.company,
    label: `${p.name}（${p.company}）`,
  }));
  const company = String(form.company ?? '').trim();
  if (company && !base.some((o) => o.value === company)) {
    const p = providers.value.find((x) => x.kind === 'api' && x.company === company);
    base.unshift({
      value: company,
      label: p
        ? `${p.name}（${p.company}，当前未同时满足激活+启用中）`
        : `${company}（目录中已有，但无匹配 API 厂商）`,
      disabled: true,
    });
  }
  return base;
});

function filterVendorCompanyOption(input: string, option: { label?: string }) {
  return (option.label || '').toLowerCase().includes(input.trim().toLowerCase());
}

async function load() {
  const [catalog, pv] = await Promise.all([fetchAIModelCatalog(), fetchAIProviders('api')]);
  rows.value = catalog;
  providers.value = pv;
}

function openCreate() {
  isCreate.value = true;
  Object.assign(form, {
    id: undefined,
    name: '',
    display_name: '',
    position: 0,
    company: '',
    is_hidden: false,
    supports_search: false,
    supports_multimodal: false,
    supports_reasoning: false,
    supports_tool_use: false,
    supports_voice_gen: false,
    supports_image_gen: false,
    price_tier: 0,
    supports_text: true,
    reasoning_controllable: false,
    source: 'custom',
    is_active: true,
  });
  modalOpen.value = true;
}

function openEdit(row: AIModelCatalog) {
  isCreate.value = false;
  Object.assign(form, { ...row, price_tier: Number(row.price_tier ?? 0) });
  modalOpen.value = true;
}

async function submit() {
  try {
    saving.value = true;
    if (isCreate.value) {
      const nm = String(form.name ?? '').trim();
      if (!nm) {
        message.warning('请录入模型唯一标识');
        return;
      }
      const co = String(form.company ?? '').trim();
      if (!co) {
        message.warning('请选择厂商信息');
        return;
      }
      form.name = nm;
      form.company = co;
      await createAIModelCatalog({
        name: nm,
        display_name: form.display_name,
        position: form.position,
        company: form.company,
        is_hidden: form.is_hidden,
        supports_search: form.supports_search,
        supports_multimodal: form.supports_multimodal,
        supports_reasoning: form.supports_reasoning,
        supports_tool_use: form.supports_tool_use,
        supports_voice_gen: form.supports_voice_gen,
        supports_image_gen: form.supports_image_gen,
        price_tier: form.price_tier,
        supports_text: form.supports_text,
        reasoning_controllable: form.reasoning_controllable,
        source: form.source,
        is_active: form.is_active,
      });
      message.success('已新增模型目录');
    } else {
      const co = String(form.company ?? '').trim();
      if (!co) {
        message.warning('请选择厂商信息');
        return;
      }
      form.company = co;
      await updateAIModelCatalog(Number(form.id), {
        display_name: form.display_name,
        position: form.position,
        company: form.company,
        is_hidden: form.is_hidden,
        supports_search: form.supports_search,
        supports_multimodal: form.supports_multimodal,
        supports_reasoning: form.supports_reasoning,
        supports_tool_use: form.supports_tool_use,
        supports_voice_gen: form.supports_voice_gen,
        supports_image_gen: form.supports_image_gen,
        price_tier: form.price_tier,
        supports_text: form.supports_text,
        reasoning_controllable: form.reasoning_controllable,
        source: form.source,
        is_active: form.is_active,
      });
      message.success('已更新模型目录');
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
