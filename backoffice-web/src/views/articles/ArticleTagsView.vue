<template>
  <a-space style="margin-bottom: 16px" wrap>
    <a-button type="primary" @click="openCreate">新增标签</a-button>
    <a-input-search v-model:value="query.q" placeholder="标签名称 / slug" enter-button style="width: 260px" @search="load" />
    <a-button @click="openMerge">合并标签</a-button>
  </a-space>
  <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
    <a-table-column title="名称" data-index="name" />
    <a-table-column title="Slug" data-index="slug" />
    <a-table-column title="文章数" data-index="article_count" width="100" />
    <a-table-column title="状态" key="active" width="90">
      <template #default="{ record }"><a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '停用' }}</a-tag></template>
    </a-table-column>
    <a-table-column title="操作" key="actions" width="170">
      <template #default="{ record }">
        <a-space>
          <a-button size="small" @click="openEdit(record)">编辑</a-button>
          <a-button size="small" danger @click="remove(record.id)">删除/停用</a-button>
        </a-space>
      </template>
    </a-table-column>
  </a-table>
  <a-pagination style="margin-top: 16px; text-align: right" :current="query.page" :page-size="query.page_size" :total="pagination.total" @change="onPageChange" />

  <a-modal v-model:open="modalOpen" :title="editingId ? '编辑标签' : '新增标签'" @ok="submit">
    <a-form layout="vertical">
      <a-form-item label="名称"><a-input v-model:value="form.name" /></a-form-item>
      <a-form-item label="Slug"><a-input v-model:value="form.slug" /></a-form-item>
      <a-form-item label="描述"><a-input v-model:value="form.description" /></a-form-item>
      <a-form-item label="启用"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="mergeOpen" title="合并标签" @ok="submitMerge">
    <a-form layout="vertical">
      <a-form-item label="源标签"><a-select v-model:value="mergeForm.source_tag_id" :options="tagOptions" /></a-form-item>
      <a-form-item label="目标标签"><a-select v-model:value="mergeForm.target_tag_id" :options="tagOptions" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { createArticleTag, deleteArticleTag, fetchArticleTags, mergeArticleTags, updateArticleTag, type ArticleTag } from '../../api/modules/articles';
import type { Pagination } from '../../types';

const loading = ref(false);
const rows = ref<ArticleTag[]>([]);
const modalOpen = ref(false);
const mergeOpen = ref(false);
const editingId = ref<number | null>(null);
const form = reactive<Record<string, any>>({});
const mergeForm = reactive({ source_tag_id: undefined as number | undefined, target_tag_id: undefined as number | undefined });
const query = reactive({ page: 1, page_size: 20, q: '' });
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const tagOptions = computed(() => rows.value.map((item) => ({ value: item.id, label: item.name })));

async function load() {
  loading.value = true;
  try {
    const data = await fetchArticleTags(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, { name: '', slug: '', description: '', is_active: true });
  modalOpen.value = true;
}
function openEdit(row: ArticleTag) {
  editingId.value = row.id;
  Object.assign(form, row);
  modalOpen.value = true;
}
async function submit() {
  if (editingId.value) {
    await updateArticleTag(editingId.value, form);
    message.success('已更新标签');
  } else {
    await createArticleTag(form);
    message.success('已新增标签');
  }
  modalOpen.value = false;
  await load();
}
function remove(id: number) {
  Modal.confirm({
    title: '删除或停用标签',
    content: '有关联文章时会自动停用。',
    onOk: async () => {
      await deleteArticleTag(id);
      message.success('已处理');
      await load();
    },
  });
}
function openMerge() {
  Object.assign(mergeForm, { source_tag_id: undefined, target_tag_id: undefined });
  mergeOpen.value = true;
}
async function submitMerge() {
  if (!mergeForm.source_tag_id || !mergeForm.target_tag_id) return;
  await mergeArticleTags({ source_tag_id: mergeForm.source_tag_id, target_tag_id: mergeForm.target_tag_id });
  message.success('已合并标签');
  mergeOpen.value = false;
  await load();
}
function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}
onMounted(load);
</script>
