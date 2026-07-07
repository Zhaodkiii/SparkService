<template>
  <a-card title="阅读数据" :bordered="false">
    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :scroll="{ x: 1000 }">
      <a-table-column title="文章" data-index="title" />
      <a-table-column title="语言" data-index="locale" width="100" />
      <a-table-column title="点击量" data-index="view_count" width="110" />
      <a-table-column title="有效阅读" data-index="read_count" width="110" />
      <a-table-column title="累计阅读秒数" data-index="reading_time_seconds" width="140" />
      <a-table-column title="平均阅读秒数" data-index="average_reading_time_seconds" width="140" />
      <a-table-column title="发布时间" key="published_at" width="180">
        <template #default="{ record }">{{ formatDateTime(record.published_at) }}</template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchArticleAnalytics, type ArticleRow } from '../../api/modules/articles';
import { formatDateTime } from '../../utils/datetime';

const loading = ref(false);
const rows = ref<ArticleRow[]>([]);
async function load() {
  loading.value = true;
  try {
    rows.value = (await fetchArticleAnalytics()).items;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
