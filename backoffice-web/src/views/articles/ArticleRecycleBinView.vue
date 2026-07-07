<template>
  <a-card title="回收站" :bordered="false">
    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
      <a-table-column title="标题" data-index="title" />
      <a-table-column title="语言" data-index="locale" width="100" />
      <a-table-column title="删除时间" key="deleted_at" width="180">
        <template #default="{ record }">{{ formatDateTime(record.deleted_at) }}</template>
      </a-table-column>
      <a-table-column title="操作" key="actions" width="100">
        <template #default="{ record }"><a-button size="small" @click="restore(record.id)">恢复</a-button></template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchArticles, restoreArticle, type ArticleRow } from '../../api/modules/articles';
import { formatDateTime } from '../../utils/datetime';

const loading = ref(false);
const rows = ref<ArticleRow[]>([]);
async function load() {
  loading.value = true;
  try {
    rows.value = (await fetchArticles({ page: 1, page_size: 100, deleted: true })).items;
  } finally {
    loading.value = false;
  }
}
async function restore(id: number) {
  await restoreArticle(id, { comment: '后台恢复' });
  message.success('已恢复为草稿');
  await load();
}
onMounted(load);
</script>
