<template>
  <a-card :bordered="false">
    <template #title>来源合规</template>
    <a-alert style="margin-bottom: 16px" type="warning" show-icon message="以下文章缺少来源链接和参考文献，发布前需要补充。" />
    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
      <a-table-column title="标题" data-index="title" />
      <a-table-column title="语言" data-index="locale" width="100" />
      <a-table-column title="状态" key="status" width="100">
        <template #default="{ record }"><ArticleStatusBadge :status="record.status" :label="record.status_label" /></template>
      </a-table-column>
      <a-table-column title="更新时间" key="updated_at" width="180">
        <template #default="{ record }">{{ formatDateTime(record.updated_at) }}</template>
      </a-table-column>
      <a-table-column title="操作" key="actions" width="120">
        <template #default="{ record }"><a-button size="small" @click="router.push(`/articles/${record.id}/edit`)">补充来源</a-button></template>
      </a-table-column>
    </a-table>
    <a-pagination style="margin-top: 16px; text-align: right" :current="query.page" :page-size="query.page_size" :total="pagination.total" @change="onPageChange" />
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchArticleCompliance, type ArticleRow } from '../../api/modules/articles';
import type { Pagination } from '../../types';
import { formatDateTime } from '../../utils/datetime';
import ArticleStatusBadge from '../../components/articles/ArticleStatusBadge.vue';

const router = useRouter();
const loading = ref(false);
const rows = ref<ArticleRow[]>([]);
const query = reactive({ page: 1, page_size: 20 });
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
async function load() {
  loading.value = true;
  try {
    const data = await fetchArticleCompliance(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}
function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}
onMounted(load);
</script>
