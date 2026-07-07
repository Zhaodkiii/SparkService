<template>
  <a-space style="margin-bottom: 16px">
    <a-button type="primary" @click="openCreate">新增分类</a-button>
    <a-button :loading="loading" @click="load">刷新</a-button>
  </a-space>
  <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :columns="columns">
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'active'"><a-tag :color="record.is_active ? 'green' : 'red'">{{ record.is_active ? '启用' : '停用' }}</a-tag></template>
      <template v-if="column.key === 'actions'">
        <a-space>
          <a-button size="small" @click="openEdit(record)">编辑</a-button>
          <a-button size="small" danger @click="remove(record.id)">删除/停用</a-button>
        </a-space>
      </template>
    </template>
  </a-table>

  <a-modal v-model:open="modalOpen" :title="editingId ? '编辑分类' : '新增分类'" @ok="submit">
    <a-form layout="vertical">
      <a-form-item label="名称"><a-input v-model:value="form.name" /></a-form-item>
      <a-form-item label="Slug"><a-input v-model:value="form.slug" /></a-form-item>
      <a-form-item label="父级"><a-select v-model:value="form.parent_id" :options="parentOptions" /></a-form-item>
      <a-form-item label="描述"><a-input v-model:value="form.description" /></a-form-item>
      <a-form-item label="排序"><a-input-number v-model:value="form.sort_order" style="width: 100%" /></a-form-item>
      <a-form-item label="启用"><a-switch v-model:checked="form.is_active" /></a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { createArticleCategory, deleteArticleCategory, fetchArticleCategories, updateArticleCategory, type ArticleCategory } from '../../api/modules/articles';

const loading = ref(false);
const rows = ref<ArticleCategory[]>([]);
const modalOpen = ref(false);
const editingId = ref<number | null>(null);
const form = reactive<Record<string, any>>({});
const columns = [
  { title: '名称', dataIndex: 'name' },
  { title: 'Slug', dataIndex: 'slug' },
  { title: '排序', dataIndex: 'sort_order', width: 90 },
  { title: '状态', key: 'active', width: 90 },
  { title: '操作', key: 'actions', width: 160 },
];

const parentOptions = computed(() => [{ value: 0, label: '顶级分类' }, ...flatten(rows.value).map((item) => ({ value: item.id, label: item.name }))]);

function flatten(items: ArticleCategory[], prefix = ''): ArticleCategory[] {
  return items.flatMap((item) => [{ ...item, name: `${prefix}${item.name}` }, ...flatten(item.children || [], `${prefix}${item.name} / `)]);
}

async function load() {
  loading.value = true;
  try {
    rows.value = await fetchArticleCategories({ tree: true, include_inactive: true });
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  Object.assign(form, { name: '', slug: '', parent_id: 0, description: '', sort_order: 0, is_active: true });
  modalOpen.value = true;
}

function openEdit(row: ArticleCategory) {
  editingId.value = row.id;
  Object.assign(form, row);
  modalOpen.value = true;
}

async function submit() {
  if (editingId.value) {
    await updateArticleCategory(editingId.value, form);
    message.success('已更新分类');
  } else {
    await createArticleCategory(form);
    message.success('已新增分类');
  }
  modalOpen.value = false;
  await load();
}

function remove(id: number) {
  Modal.confirm({
    title: '删除或停用分类',
    content: '有关联文章或子分类时会自动停用。',
    onOk: async () => {
      await deleteArticleCategory(id);
      message.success('已处理');
      await load();
    },
  });
}

onMounted(load);
</script>
