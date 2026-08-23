<template>
  <div v-if="!isSuperAdmin" class="access-denied">
    <a-result status="403" title="无权限访问" sub-title="快捷问题配置仅面向系统管理员开放。" />
  </div>

  <template v-else>
    <div class="page-header">
      <div>
        <div class="page-title">对话 / 快捷问题配置</div>
        <div class="page-desc">管理固定快捷问题，并查看客户端 AI 生成的科普问题登记与点击情况</div>
      </div>
      <a-button v-if="activeTab === 'config'" type="primary" @click="openCreate">新增问题</a-button>
    </div>

    <a-tabs v-model:active-key="activeTab">
      <!-- 配置管理 -->
      <a-tab-pane key="config" tab="配置管理">
        <a-space wrap style="margin-bottom: 16px">
          <a-input-search
            v-model:value="configQuery.keyword"
            placeholder="标题 / prompt"
            enter-button
            style="width: 240px"
            @search="loadConfigs"
          />
          <a-input v-model:value="configQuery.category" placeholder="分类" allow-clear style="width: 140px" @pressEnter="loadConfigs" />
          <a-input v-model:value="configQuery.locale" placeholder="语言" allow-clear style="width: 120px" @pressEnter="loadConfigs" />
          <a-select v-model:value="configQuery.is_active" style="width: 120px" @change="loadConfigs">
            <a-select-option value="">全部状态</a-select-option>
            <a-select-option value="true">启用</a-select-option>
            <a-select-option value="false">停用</a-select-option>
          </a-select>
          <a-button type="primary" @click="loadConfigs">查询</a-button>
          <a-button @click="resetConfigQuery">重置</a-button>
        </a-space>

        <a-table :data-source="configRows" row-key="id" :pagination="false" :loading="configLoading">
          <a-table-column title="问题标题" data-index="title" :ellipsis="true" />
          <a-table-column title="Prompt 预览" data-index="prompt_preview" :ellipsis="true" />
          <a-table-column title="分类" data-index="category" :width="120" />
          <a-table-column title="语言" data-index="locale" :width="100" />
          <a-table-column title="状态" key="is_active" :width="90">
            <template #default="{ record }">
              <a-tag :color="record.is_active ? 'green' : 'default'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="创建人" data-index="created_by_name" :width="120" />
          <a-table-column title="最近更新" key="updated_at" :width="170">
            <template #default="{ record }">{{ formatDateTime(record.updated_at) }}</template>
          </a-table-column>
          <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
            <template #default="{ record }">
              <TableHoverActions>
                <a-button size="small" @click="openEdit(record)">编辑</a-button>
                <a-button v-if="!record.is_active" size="small" type="primary" @click="toggleEnable(record, true)">启用</a-button>
                <a-button v-else size="small" danger @click="toggleEnable(record, false)">停用</a-button>
              </TableHoverActions>
            </template>
          </a-table-column>
        </a-table>

        <a-pagination
          style="margin-top: 16px; text-align: right"
          :current="configQuery.page"
          :page-size="configQuery.page_size"
          :total="configPagination.total"
          @change="onConfigPageChange"
        />
      </a-tab-pane>

      <!-- 生成记录 -->
      <a-tab-pane key="records" tab="生成记录">
        <a-space wrap style="margin-bottom: 16px">
          <a-input-search
            v-model:value="recordsQuery.keyword"
            placeholder="标题 / prompt"
            enter-button
            style="width: 240px"
            @search="loadRecords"
          />
          <a-input v-model:value="recordsQuery.user_id" placeholder="用户 ID" style="width: 110px" @pressEnter="loadRecords" />
          <a-input v-model:value="recordsQuery.member_id" placeholder="成员 ID" style="width: 110px" @pressEnter="loadRecords" />
          <a-input v-model:value="recordsQuery.category" placeholder="分类" allow-clear style="width: 130px" @pressEnter="loadRecords" />
          <a-range-picker v-model:value="dateRange" show-time format="YYYY-MM-DD HH:mm:ss" @change="onRecordDateChange" />
          <a-input v-model:value="recordsQuery.click_count_min" placeholder="最小点击" style="width: 110px" @pressEnter="loadRecords" />
          <a-input v-model:value="recordsQuery.click_count_max" placeholder="最大点击" style="width: 110px" @pressEnter="loadRecords" />
          <a-button type="primary" @click="loadRecords">查询</a-button>
          <a-button @click="resetRecordsQuery">重置</a-button>
        </a-space>

        <a-table :data-source="recordsRows" row-key="id" :pagination="false" :loading="recordsLoading">
          <a-table-column title="ID" data-index="id" :width="80" />
          <a-table-column title="问题标题" data-index="title" :ellipsis="true" />
          <a-table-column title="Prompt 预览" data-index="prompt_preview" :ellipsis="true" />
          <a-table-column title="用户" key="user" :width="160">
            <template #default="{ record }">
              <div>{{ record.user_name }}</div>
              <div class="sub-text">#{{ record.user }}</div>
            </template>
          </a-table-column>
          <a-table-column title="成员" key="member" :width="160">
            <template #default="{ record }">
              <div>{{ record.member_name }}</div>
              <div class="sub-text">#{{ record.member }}</div>
            </template>
          </a-table-column>
          <a-table-column title="点击次数" data-index="click_count" :width="100" />
          <a-table-column title="创建时间" key="created_at" :width="170">
            <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
          </a-table-column>
          <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
            <template #default="{ record }">
              <TableHoverActions>
                <a-button size="small" type="primary" @click="openRecordDetail(record)">查看详情</a-button>
              </TableHoverActions>
            </template>
          </a-table-column>
        </a-table>

        <a-pagination
          style="margin-top: 16px; text-align: right"
          :current="recordsQuery.page"
          :page-size="recordsQuery.page_size"
          :total="recordsPagination.total"
          @change="onRecordsPageChange"
        />
      </a-tab-pane>
    </a-tabs>

    <!-- 新增 / 编辑弹窗 -->
    <a-modal
      v-model:open="modalOpen"
      :title="modalMode === 'create' ? '新增快捷问题' : '编辑快捷问题'"
      :confirm-loading="saving"
      @ok="saveConfig"
    >
      <a-form layout="vertical">
        <a-form-item label="展示文案 (title)" required>
          <a-input v-model:value="form.title" placeholder="短句，建议不超过 30 个中文字符" :maxlength="120" />
        </a-form-item>
        <a-form-item label="完整 prompt" required>
          <a-textarea v-model:value="form.prompt" :rows="4" placeholder="点击后发送给 AI 的完整 prompt" />
        </a-form-item>
        <a-form-item label="分类 (category)">
          <a-input v-model:value="form.category" placeholder="popular_science" />
        </a-form-item>
        <a-form-item label="语言 (locale)">
          <a-input v-model:value="form.locale" placeholder="zh-Hans" />
        </a-form-item>
        <a-form-item label="是否启用">
          <a-switch v-model:checked="form.is_active" />
        </a-form-item>
        <a-form-item label="备注 / 标签 (metadata, JSON 对象)">
          <a-textarea v-model:value="form.metadata" :rows="2" placeholder='例如 {"scene": "onboarding"}' />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 生成记录详情抽屉 -->
    <a-drawer v-model:open="drawerOpen" title="生成记录详情" :width="480">
      <template v-if="recordDetail">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="ID">
            {{ recordDetail.id }}
            <a-button type="link" size="small" @click="copy(String(recordDetail.id))">复制</a-button>
          </a-descriptions-item>
          <a-descriptions-item label="标题">{{ recordDetail.title }}</a-descriptions-item>
          <a-descriptions-item label="分类">{{ recordDetail.category }}</a-descriptions-item>
          <a-descriptions-item label="用户 ID">
            {{ recordDetail.user }}
            <a-button type="link" size="small" @click="copy(String(recordDetail.user))">复制</a-button>
          </a-descriptions-item>
          <a-descriptions-item label="成员 ID">
            {{ recordDetail.member }}
            <a-button type="link" size="small" @click="copy(String(recordDetail.member))">复制</a-button>
          </a-descriptions-item>
          <a-descriptions-item label="点击次数">{{ recordDetail.click_count }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ formatDateTime(recordDetail.created_at) }}</a-descriptions-item>
        </a-descriptions>
        <div class="prompt-block">
          <div class="prompt-block-title">完整 prompt</div>
          <div class="prompt-block-body">{{ recordDetail.prompt }}</div>
          <a-button size="small" type="primary" @click="copy(recordDetail.prompt)">复制 prompt</a-button>
        </div>
      </template>
    </a-drawer>
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import TableHoverActions from '../components/TableHoverActions.vue';
import {
  createQuickQuestionConfig,
  disableQuickQuestionConfig,
  enableQuickQuestionConfig,
  fetchGeneratedQuestionRecords,
  fetchQuickQuestionConfigs,
  updateQuickQuestionConfig,
  type GeneratedQuestionRecord,
  type QuickQuestionConfig,
} from '../api/modules/conversationQuickQuestions';
import { useAuthStore } from '../stores/auth';
import type { Pagination } from '../types';
import { copyText } from '../utils/clipboard';
import { formatDateTime } from '../utils/datetime';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const auth = useAuthStore();
const isSuperAdmin = computed(() => !!auth.user?.is_superuser);
const actionsColWidth = calcActionsColWidth({ buttons: 2 });

const activeTab = ref<'config' | 'records'>('config');

// ---------- 配置管理 ----------
const configQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: '',
  category: '',
  locale: '',
  is_active: '',
});
const configRows = ref<QuickQuestionConfig[]>([]);
const configPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const configLoading = ref(false);

// ---------- 生成记录 ----------
const recordsQuery = reactive({
  page: 1,
  page_size: 20,
  keyword: '',
  user_id: '',
  member_id: '',
  category: '',
  created_at_start: '',
  created_at_end: '',
  click_count_min: '',
  click_count_max: '',
});
const recordsRows = ref<GeneratedQuestionRecord[]>([]);
const recordsPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const recordsLoading = ref(false);
const dateRange = ref<[Dayjs, Dayjs] | null>(null);

// ---------- 编辑弹窗 ----------
const modalOpen = ref(false);
const saving = ref(false);
const modalMode = ref<'create' | 'edit'>('create');
const editingId = ref<number | null>(null);
const form = reactive({
  title: '',
  prompt: '',
  category: 'popular_science',
  locale: 'zh-Hans',
  is_active: true,
  metadata: '',
});

// ---------- 详情抽屉 ----------
const drawerOpen = ref(false);
const recordDetail = ref<GeneratedQuestionRecord | null>(null);

async function loadConfigs() {
  if (!isSuperAdmin.value) return;
  configLoading.value = true;
  try {
    const data = await fetchQuickQuestionConfigs({ ...configQuery });
    configRows.value = data.items;
    Object.assign(configPagination, data.pagination);
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    configLoading.value = false;
  }
}

async function loadRecords() {
  if (!isSuperAdmin.value) return;
  recordsLoading.value = true;
  try {
    const data = await fetchGeneratedQuestionRecords({ ...recordsQuery });
    recordsRows.value = data.items;
    Object.assign(recordsPagination, data.pagination);
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    recordsLoading.value = false;
  }
}

function resetConfigQuery() {
  configQuery.page = 1;
  configQuery.keyword = '';
  configQuery.category = '';
  configQuery.locale = '';
  configQuery.is_active = '';
  loadConfigs();
}

function resetRecordsQuery() {
  recordsQuery.page = 1;
  recordsQuery.keyword = '';
  recordsQuery.user_id = '';
  recordsQuery.member_id = '';
  recordsQuery.category = '';
  recordsQuery.created_at_start = '';
  recordsQuery.created_at_end = '';
  recordsQuery.click_count_min = '';
  recordsQuery.click_count_max = '';
  dateRange.value = null;
  loadRecords();
}

function onConfigPageChange(page: number, pageSize: number) {
  configQuery.page = page;
  configQuery.page_size = pageSize;
  loadConfigs();
}

function onRecordsPageChange(page: number, pageSize: number) {
  recordsQuery.page = page;
  recordsQuery.page_size = pageSize;
  loadRecords();
}

function onRecordDateChange(values: [Dayjs, Dayjs] | [string, string] | null) {
  if (!values || !Array.isArray(values) || values.length !== 2) {
    recordsQuery.created_at_start = '';
    recordsQuery.created_at_end = '';
  } else {
    recordsQuery.created_at_start = dayjs(values[0]).toISOString();
    recordsQuery.created_at_end = dayjs(values[1]).toISOString();
  }
  loadRecords();
}

function openCreate() {
  modalMode.value = 'create';
  editingId.value = null;
  form.title = '';
  form.prompt = '';
  form.category = 'popular_science';
  form.locale = 'zh-Hans';
  form.is_active = true;
  form.metadata = '';
  modalOpen.value = true;
}

function openEdit(record: QuickQuestionConfig) {
  modalMode.value = 'edit';
  editingId.value = record.id;
  form.title = record.title;
  form.prompt = record.prompt;
  form.category = record.category;
  form.locale = record.locale;
  form.is_active = record.is_active;
  form.metadata = record.metadata && Object.keys(record.metadata).length ? JSON.stringify(record.metadata) : '';
  modalOpen.value = true;
}

function parseMetadata(): Record<string, unknown> | undefined {
  const raw = form.metadata.trim();
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // fallthrough
  }
  throw new Error('metadata 需为合法 JSON 对象');
}

async function saveConfig() {
  if (!form.title.trim()) {
    message.error('请填写展示文案 title');
    return;
  }
  if (!form.prompt.trim()) {
    message.error('请填写完整 prompt');
    return;
  }
  let metadata: Record<string, unknown> | undefined;
  try {
    metadata = parseMetadata();
  } catch (error: any) {
    message.error(error?.message || 'metadata 非法');
    return;
  }

  saving.value = true;
  try {
    if (modalMode.value === 'create') {
      await createQuickQuestionConfig({
        title: form.title.trim(),
        prompt: form.prompt.trim(),
        category: form.category.trim() || 'popular_science',
        locale: form.locale.trim() || 'zh-Hans',
        is_active: form.is_active,
        metadata,
      });
      message.success('新增成功');
    } else if (editingId.value != null) {
      await updateQuickQuestionConfig(editingId.value, {
        title: form.title.trim(),
        prompt: form.prompt.trim(),
        category: form.category.trim() || 'popular_science',
        locale: form.locale.trim() || 'zh-Hans',
        metadata,
      });
      message.success('保存成功');
      // PATCH 不修改启停状态，等列表刷新即可；此处单独不处理 is_active。
      if (form.is_active !== undefined) {
        const target = configRows.value.find((r) => r.id === editingId.value);
        if (target && target.is_active !== form.is_active) {
          const next = form.is_active ? enableQuickQuestionConfig : disableQuickQuestionConfig;
          await next(editingId.value);
        }
      }
    }
    modalOpen.value = false;
    loadConfigs();
  } catch (error: any) {
    message.error(error?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

function toggleEnable(record: QuickQuestionConfig, enable: boolean) {
  if (!enable) {
    Modal.confirm({
      title: '确认停用',
      content: `确定停用「${record.title}」吗？停用后不影响历史生成记录与点击统计。`,
      onOk: async () => {
        try {
          await disableQuickQuestionConfig(record.id);
          message.success('已停用');
          loadConfigs();
        } catch (error: any) {
          message.error(error?.message || '操作失败');
        }
      },
    });
    return;
  }
  enableQuickQuestionConfig(record.id)
    .then(() => {
      message.success('已启用');
      loadConfigs();
    })
    .catch((error: any) => message.error(error?.message || '操作失败'));
}

function openRecordDetail(record: GeneratedQuestionRecord) {
  // 列表序列化器已返回完整 prompt，直接复用当前行数据。
  recordDetail.value = record;
  drawerOpen.value = true;
}

async function copy(text: string) {
  const ok = await copyText(text);
  if (ok) {
    message.success('已复制');
  } else {
    message.error('复制失败');
  }
}

onMounted(async () => {
  loadConfigs();
  loadRecords();
});
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
}
.page-desc {
  color: #666;
  margin-top: 4px;
}
.sub-text {
  color: #999;
  font-size: 12px;
}
.prompt-block {
  margin-top: 16px;
}
.prompt-block-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.prompt-block-body {
  background: #fafafa;
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 8px;
}
.access-denied {
  padding: 48px 0;
}
</style>