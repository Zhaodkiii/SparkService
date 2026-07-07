<template>
  <a-row :gutter="16">
    <a-col v-for="card in cards" :key="card.title" :xs="24" :md="12" :xl="6">
      <a-card :title="card.title" :bordered="false" style="margin-bottom: 16px">
        <div class="metric">{{ card.value }}</div>
      </a-card>
    </a-col>
  </a-row>
  <a-row :gutter="16">
    <a-col :xs="24" :lg="12">
      <a-card title="热门文章" :bordered="false">
        <a-list :data-source="data?.popular_articles || []" :loading="loading">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.title" :description="`${item.locale} · 点击 ${item.view_count}`" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>
    <a-col :xs="24" :lg="12">
      <a-card title="最近发布" :bordered="false">
        <a-list :data-source="data?.recent_articles || []" :loading="loading">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.title" :description="formatDateTime(item.published_at)" />
            </a-list-item>
          </template>
        </a-list>
      </a-card>
    </a-col>
  </a-row>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchArticleOverview, type ArticleOverview } from '../../api/modules/articles';
import { formatDateTime } from '../../utils/datetime';

const loading = ref(false);
const data = ref<ArticleOverview | null>(null);
const cards = computed(() => [
  { title: '文章总数', value: data.value?.total ?? '-' },
  { title: '已发布', value: data.value?.published ?? '-' },
  { title: '草稿', value: data.value?.draft ?? '-' },
  { title: '近 7 日点击', value: data.value?.recent_7d_views ?? '-' },
  { title: '缺少来源', value: data.value?.missing_reference ?? '-' },
  { title: '需复查', value: data.value?.stale_review ?? '-' },
  { title: '总点击量', value: data.value?.total_views ?? '-' },
  { title: '累计阅读秒数', value: data.value?.total_read_seconds ?? '-' },
]);

async function load() {
  loading.value = true;
  try {
    data.value = await fetchArticleOverview();
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.metric {
  font-size: 26px;
  font-weight: 700;
}
</style>
