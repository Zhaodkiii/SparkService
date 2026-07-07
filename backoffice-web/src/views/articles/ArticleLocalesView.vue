<template>
  <a-card title="多语言管理" :bordered="false">
    <a-alert type="info" show-icon message="当前一期已支持文章语言和翻译组字段。本页展示不同语言文章，后续可扩展为翻译组工作台。" style="margin-bottom: 16px" />
    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
      <a-table-column title="标题" data-index="title" />
      <a-table-column title="语言" data-index="locale" width="120" />
      <a-table-column title="翻译组" data-index="translation_group_id" width="140" />
      <a-table-column title="状态" key="status" width="100">
        <template #default="{ record }"><ArticleStatusBadge :status="record.status" :label="record.status_label" /></template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchArticles, type ArticleRow } from '../../api/modules/articles';
import ArticleStatusBadge from '../../components/articles/ArticleStatusBadge.vue';

const loading = ref(false);
const rows = ref<ArticleRow[]>([]);
async function load() {
  loading.value = true;
  try {
    rows.value = (await fetchArticles({ page: 1, page_size: 100 })).items;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
