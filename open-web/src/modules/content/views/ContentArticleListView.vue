<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppOpenBanner from '../../../shared/components/AppOpenBanner.vue';
import PublicPageShell from '../../../shared/components/PublicPageShell.vue';
import { useDocumentMeta } from '../../../shared/composables/useDocumentMeta';
import { usePublicShare } from '../../../shared/composables/usePublicShare';
import {
  fetchPublicArticleList,
  fetchPublicCategories,
  fetchPublicTags,
} from '../api/contentApi';
import ContentArticleCard from '../components/ContentArticleCard.vue';
import ContentArticleErrorState from '../components/ContentArticleErrorState.vue';
import ContentCategoryTabs from '../components/ContentCategoryTabs.vue';
import ContentTagFilter from '../components/ContentTagFilter.vue';
import type {
  ContentErrorKind,
  PublicContentArticleListItem,
  PublicContentCategoryNode,
  PublicContentTag,
} from '../types';

const route = useRoute();
const router = useRouter();
const { updateMeta } = useDocumentMeta();
const { openApp } = usePublicShare();

const defaultLocale = import.meta.env.VITE_DEFAULT_LOCALE || 'zh-CN';

const articles = ref<PublicContentArticleListItem[]>([]);
const categories = ref<PublicContentCategoryNode[]>([]);
const tags = ref<PublicContentTag[]>([]);
const phase = ref<ContentErrorKind>('loading');
const isLoadingMore = ref(false);
const currentPage = ref(1);
const totalPages = ref(1);
const sentinel = ref<HTMLElement | null>(null);

let observer: IntersectionObserver | null = null;

const locale = computed(() => {
  const q = route.query.locale;
  return typeof q === 'string' && q ? q : defaultLocale;
});

const categoryId = computed(() => {
  const raw = route.query.category_id;
  if (raw === undefined || raw === null || raw === '') return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
});

const tagId = computed(() => {
  const raw = route.query.tag_id;
  if (raw === undefined || raw === null || raw === '') return null;
  const id = Number(raw);
  return Number.isFinite(id) ? id : null;
});

const hasMore = computed(() => currentPage.value < totalPages.value);

const listTitle = computed(() => {
  if (tagId.value !== null) {
    const tag = tags.value.find((item) => item.id === tagId.value);
    if (tag) return `${tag.name} - 健康科普`;
  }
  if (categoryId.value !== null) {
    const category = categories.value.find((item) => item.id === categoryId.value);
    if (category) return `${category.name} - 健康科普`;
  }
  return '健康科普';
});

function buildQuery(overrides: { category_id?: number | null; tag_id?: number | null } = {}) {
  const query: Record<string, string> = {};
  const nextCategoryId =
    overrides.category_id !== undefined ? overrides.category_id : categoryId.value;
  const nextTagId = overrides.tag_id !== undefined ? overrides.tag_id : tagId.value;

  if (nextCategoryId !== null) query.category_id = String(nextCategoryId);
  if (nextTagId !== null) query.tag_id = String(nextTagId);
  if (locale.value !== defaultLocale) query.locale = locale.value;

  return query;
}

function setCategoryId(id: number | null) {
  router.push({ name: 'content-article-list', query: buildQuery({ category_id: id }) });
}

function setTagId(id: number | null) {
  router.push({ name: 'content-article-list', query: buildQuery({ tag_id: id }) });
}

function classifyError(err: unknown): ContentErrorKind {
  const message = err instanceof Error ? err.message : '';
  if (message.includes('Network Error') || message === 'request_failed') return 'network';
  return 'unavailable';
}

async function loadFilters() {
  const [categoryData, tagData] = await Promise.all([
    fetchPublicCategories(),
    fetchPublicTags(locale.value),
  ]);
  categories.value = categoryData;
  tags.value = tagData;
}

async function loadArticles(reset = true) {
  if (reset) {
    phase.value = 'loading';
    articles.value = [];
    currentPage.value = 1;
    totalPages.value = 1;
  } else {
    if (isLoadingMore.value || !hasMore.value) return;
    isLoadingMore.value = true;
  }

  const page = reset ? 1 : currentPage.value + 1;

  try {
    const params: Record<string, string | number> = {
      locale: locale.value,
      page,
      page_size: 20,
    };
    if (categoryId.value !== null) params.category_id = categoryId.value;
    if (tagId.value !== null) params.tag_id = tagId.value;

    const data = await fetchPublicArticleList(params);
    articles.value = reset ? data.items : [...articles.value, ...data.items];
    currentPage.value = data.pagination.page;
    totalPages.value = data.pagination.total_pages;
    phase.value = 'success';
  } catch (err) {
    if (reset) {
      phase.value = classifyError(err);
    }
  } finally {
    isLoadingMore.value = false;
  }
}

async function reloadAll() {
  try {
    await loadFilters();
    await loadArticles(true);
    updateMeta({ title: listTitle.value, description: '小鲸健康科普文章' });
    await nextTick();
    setupObserver();
  } catch {
    phase.value = 'unavailable';
  }
}

function setupObserver() {
  observer?.disconnect();
  if (!sentinel.value) return;

  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry?.isIntersecting && hasMore.value && !isLoadingMore.value && phase.value === 'success') {
        loadArticles(false);
      }
    },
    { rootMargin: '200px' },
  );
  observer.observe(sentinel.value);
}

watch([categoryId, tagId, locale], () => {
  reloadAll();
}, { immediate: true });

onUnmounted(() => {
  observer?.disconnect();
});
</script>

<template>
  <PublicPageShell>
    <template #banner>
      <AppOpenBanner @open-app="openApp()" />
    </template>

    <div class="content-list">
      <header class="content-list__header">
        <h1 class="content-list__title">{{ listTitle }}</h1>
      </header>

      <div class="content-list__filters">
        <ContentCategoryTabs
          :categories="categories"
          :model-value="categoryId"
          @update:model-value="setCategoryId"
        />
        <ContentTagFilter
          :tags="tags"
          :model-value="tagId"
          @update:model-value="setTagId"
        />
      </div>

      <ContentArticleErrorState
        v-if="phase !== 'success'"
        :kind="phase"
        @retry="reloadAll"
      />

      <template v-else>
        <p v-if="!articles.length" class="content-list__empty">暂无相关文章</p>

        <div v-else class="content-list__grid">
          <ContentArticleCard
            v-for="article in articles"
            :key="article.id"
            :article="article"
            @category-click="setCategoryId"
            @tag-click="setTagId"
          />
        </div>

        <div
          v-if="hasMore"
          ref="sentinel"
          class="content-list__sentinel"
          role="status"
          aria-live="polite"
        >
          <span v-if="isLoadingMore" class="content-list__loading-more">加载中...</span>
        </div>

        <p v-else-if="articles.length" class="content-list__end">已加载全部内容</p>
      </template>
    </div>
  </PublicPageShell>
</template>

<style scoped>
.content-list__header {
  padding: 16px 0 4px;
}

.content-list__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #111;
}

.content-list__filters {
  position: sticky;
  top: 0;
  z-index: 40;
  margin: 0 -20px;
  padding: 0 20px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

.content-list__empty {
  margin: 48px 0;
  font-size: 15px;
  text-align: center;
  color: #888;
}

.content-list__grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 16px;
}

.content-list__sentinel {
  display: flex;
  justify-content: center;
  min-height: 48px;
  padding: 16px 0 8px;
}

.content-list__loading-more {
  font-size: 14px;
  color: #888;
}

.content-list__end {
  margin: 8px 0 0;
  padding-bottom: 8px;
  font-size: 13px;
  text-align: center;
  color: #aaa;
}
</style>
