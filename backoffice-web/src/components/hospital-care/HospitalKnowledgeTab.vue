<template>
  <div>
    <a-space wrap style="margin-bottom: 16px">
      <a-input-search v-model:value="query" placeholder="搜索知识库" style="width: 240px" @search="loadList" />
      <a-select v-model:value="departmentId" style="width: 180px" allow-clear placeholder="科室" @change="loadList">
        <a-select-option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
      </a-select>
      <a-button v-if="canCreate" type="primary" @click="openEditor(null)">+ 新建知识库</a-button>
    </a-space>

    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
      <a-table-column title="名称" data-index="name" />
      <a-table-column title="科室" key="depts" :width="180">
        <template #default="{ record }">{{ (record.departments || []).map((item) => item.name).join('、') || '--' }}</template>
      </a-table-column>
      <a-table-column title="文本" key="docs" :width="80">
        <template #default="{ record }">{{ record.document_count ?? 0 }}</template>
      </a-table-column>
      <a-table-column title="智能体" key="agents" :width="80">
        <template #default="{ record }">{{ record.agent_count ?? 0 }}</template>
      </a-table-column>
      <a-table-column title="向量" key="vector" :width="140">
        <template #default="{ record }">
          <a-tag :color="VECTOR_STATUS_COLOR[record.vector_status]">{{ VECTOR_STATUS_LABEL[record.vector_status] }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="操作" key="actions" :width="220">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" @click="openDetail(record)">详情</a-button>
            <a-button v-if="canUpdate" size="small" @click="openEditor(record)">编辑</a-button>
            <a-button v-if="canDelete" size="small" danger @click="confirmDelete(record)">删除</a-button>
          </TableHoverActions>
        </template>
      </a-table-column>
    </a-table>
    <a-pagination
      style="margin-top: 16px; text-align: right"
      :current="page"
      :page-size="pageSize"
      :total="total"
      @change="onPage"
    />

    <a-card v-if="detail" style="margin-top: 24px" :title="detail.name">
      <template #extra>
        <a-button type="link" @click="detail = null">收起</a-button>
      </template>
      <a-space wrap style="margin-bottom: 12px">
        <a-tag :color="VECTOR_STATUS_COLOR[detail.vector_status]">{{ VECTOR_STATUS_LABEL[detail.vector_status] }}</a-tag>
        <span>关联智能体 {{ detail.agent_count ?? 0 }} 个</span>
      </a-space>
      <p style="color: #8c8c8c">{{ detail.description || '暂无简介' }}</p>

      <a-typography-title :level="5">文本资料</a-typography-title>
      <a-button v-if="canUpdate" type="primary" size="small" style="margin-bottom: 12px" @click="openDocument(null)">+ 新建文本</a-button>
      <a-table :data-source="detail.documents || []" row-key="id" :pagination="false" size="small">
        <a-table-column title="标题" data-index="title" />
        <a-table-column title="摘要" data-index="excerpt" />
        <a-table-column title="操作" key="doc-actions" :width="160">
          <template #default="{ record }">
            <a-space>
              <a-button v-if="canUpdate" size="small" @click="openDocument(record)">编辑</a-button>
              <a-button v-if="canDelete" size="small" danger @click="confirmDeleteDocument(record)">删除</a-button>
            </a-space>
          </template>
        </a-table-column>
      </a-table>

      <a-typography-title :level="5" style="margin-top: 24px">向量生成</a-typography-title>
      <a-space wrap>
        <a-select
          v-model:value="embeddingBindingId"
          style="width: 280px"
          placeholder="选择 Embedding 模型"
          :options="embeddingOptions"
        />
        <a-button v-if="canBuild" type="primary" :loading="building" @click="buildVectors">生成向量</a-button>
      </a-space>
    </a-card>

    <HospitalKnowledgeBaseModal
      v-model:open="editor.open"
      :hospital-id="hospitalId"
      :departments="departments"
      :profile="editor.profile"
      @saved="onSaved"
    />

    <a-modal
      v-model:open="documentModal.open"
      :title="documentModal.id ? '编辑文本资料' : '新建文本资料'"
      :confirm-loading="documentModal.saving"
      @ok="submitDocument"
    >
      <a-form layout="vertical">
        <a-form-item label="标题" required>
          <a-input v-model:value="documentModal.title" />
        </a-form-item>
        <a-form-item label="正文" required>
          <a-textarea v-model:value="documentModal.content" :rows="8" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { message, Modal } from 'ant-design-vue';
import {
  buildKnowledgeVector,
  createKnowledgeDocument,
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  fetchKnowledgeBase,
  fetchKnowledgeBases,
  hospitalCareMessage,
  updateKnowledgeDocument,
  type DepartmentRow,
  type KnowledgeBaseRow,
  type KnowledgeDocumentRow,
} from '../../api/modules/hospitalCare';
import { VECTOR_STATUS_COLOR, VECTOR_STATUS_LABEL } from '../../views/hospital-care/hospitalCareLabels';
import TableHoverActions from '../TableHoverActions.vue';
import HospitalKnowledgeBaseModal from './HospitalKnowledgeBaseModal.vue';

const props = defineProps<{
  hospitalId: string;
  departments: DepartmentRow[];
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  canBuild: boolean;
}>();

const loading = ref(false);
const building = ref(false);
const query = ref('');
const departmentId = ref<string | undefined>(undefined);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const rows = ref<KnowledgeBaseRow[]>([]);
const detail = ref<KnowledgeBaseRow | null>(null);
const embeddingBindingId = ref<number | undefined>(undefined);
const editor = reactive({ open: false, profile: null as KnowledgeBaseRow | null });
const documentModal = reactive({
  open: false,
  saving: false,
  id: '',
  title: '',
  content: '',
  revision: 1,
});

const embeddingOptions = computed(() =>
  (detail.value?.embedding_bindings || []).map((item) => ({
    value: item.id,
    label: item.display_name || item.model,
  })),
);

async function loadList() {
  if (!props.hospitalId) {
    return;
  }
  loading.value = true;
  try {
    const result = await fetchKnowledgeBases(props.hospitalId, {
      page: page.value,
      page_size: pageSize.value,
      q: query.value || undefined,
      department_id: departmentId.value,
    });
    rows.value = result.items;
    total.value = result.pagination.total;
    if (detail.value) {
      const current = result.items.find((item) => item.id === detail.value?.id);
      if (current) {
        await openDetail(current);
      }
    }
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    loading.value = false;
  }
}

function onPage(next: number, size: number) {
  page.value = next;
  pageSize.value = size;
  loadList();
}

function openEditor(row: KnowledgeBaseRow | null) {
  editor.profile = row;
  editor.open = true;
}

async function openDetail(row: KnowledgeBaseRow) {
  detail.value = await fetchKnowledgeBase(row.id);
  embeddingBindingId.value = detail.value.embedding_binding_id || detail.value.embedding_bindings?.[0]?.id;
}

function confirmDelete(row: KnowledgeBaseRow) {
  Modal.confirm({
    title: '删除知识库？',
    content: '不影响患者历史对话，仅停止新检索。文本与向量容器会保留。',
    okText: '删除',
    okType: 'danger',
    async onOk() {
      await deleteKnowledgeBase(row.id, row.version);
      message.success('已删除知识库');
      if (detail.value?.id === row.id) {
        detail.value = null;
      }
      await loadList();
    },
  });
}

function openDocument(row: KnowledgeDocumentRow | null) {
  documentModal.id = row?.id || '';
  documentModal.title = row?.title || '';
  documentModal.content = row?.content || '';
  documentModal.revision = row?.revision || 1;
  documentModal.open = true;
}

async function submitDocument() {
  if (!detail.value) {
    return;
  }
  if (!documentModal.title.trim()) {
    message.error('请填写标题');
    return;
  }
  documentModal.saving = true;
  try {
    if (documentModal.id) {
      await updateKnowledgeDocument(detail.value.id, documentModal.id, {
        title: documentModal.title.trim(),
        content: documentModal.content,
        revision: documentModal.revision,
      });
    } else {
      await createKnowledgeDocument(detail.value.id, {
        title: documentModal.title.trim(),
        content: documentModal.content,
        version: detail.value.version,
      });
    }
    documentModal.open = false;
    message.success('已保存文本资料');
    await openDetail(detail.value);
    await loadList();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    documentModal.saving = false;
  }
}

function confirmDeleteDocument(row: KnowledgeDocumentRow) {
  if (!detail.value) {
    return;
  }
  const profileId = detail.value.id;
  Modal.confirm({
    title: '删除文本资料？',
    content: '不影响患者历史对话，仅停止新检索。',
    okText: '删除',
    okType: 'danger',
    async onOk() {
      await deleteKnowledgeDocument(profileId, row.id, row.revision);
      message.success('已删除文本资料');
      const current = detail.value;
      if (current) {
        await openDetail(current);
      }
      await loadList();
    },
  });
}

async function buildVectors() {
  if (!detail.value || !embeddingBindingId.value) {
    message.error('请选择 Embedding 模型');
    return;
  }
  building.value = true;
  try {
    await buildKnowledgeVector(detail.value.id, {
      version: detail.value.version,
      embedding_binding_id: embeddingBindingId.value,
    });
    message.success('已生成向量');
    await openDetail(detail.value);
    await loadList();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    building.value = false;
  }
}

async function onSaved() {
  await loadList();
}

watch(
  () => props.hospitalId,
  () => {
    page.value = 1;
    detail.value = null;
    loadList();
  },
  { immediate: true },
);

defineExpose({ loadList });
</script>
