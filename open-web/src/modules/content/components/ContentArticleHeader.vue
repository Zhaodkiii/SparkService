<script setup lang="ts">
import type { PublicContentArticle } from '../types';
import { formatDateTime } from '../../../shared/utils/datetime';

defineProps<{
  article: PublicContentArticle;
}>();
</script>

<template>
  <header class="article-header">
    <h1 class="article-header__title">{{ article.title }}</h1>
    <p v-if="article.summary" class="article-header__summary">{{ article.summary }}</p>
    <div class="article-header__meta">
      <time
        v-if="article.published_at"
        class="article-header__time"
        :datetime="article.published_at"
      >
        {{ formatDateTime(article.published_at) }}
      </time>
      <span v-if="article.estimated_reading_minutes" class="article-header__reading">
        约 {{ article.estimated_reading_minutes }} 分钟
      </span>
    </div>
    <div v-if="article.category || article.tags.length" class="article-header__tags">
      <router-link
        v-if="article.category"
        :to="{ name: 'content-article-list', query: { category_id: article.category.id } }"
        class="article-header__tag article-header__tag--category"
      >
        {{ article.category.name }}
      </router-link>
      <router-link
        v-for="tag in article.tags"
        :key="tag.id"
        :to="{ name: 'content-article-list', query: { tag_id: tag.id } }"
        class="article-header__tag"
      >
        {{ tag.name }}
      </router-link>
    </div>
    <img
      v-if="article.cover_image"
      :src="article.cover_image"
      :alt="article.title"
      class="article-header__cover"
      loading="lazy"
    />
  </header>
</template>

<style scoped>
.article-header {
  padding: 24px 0 16px;
}

.article-header__title {
  margin: 0 0 12px;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.35;
  color: #111;
}

.article-header__summary {
  margin: 0 0 16px;
  font-size: 16px;
  line-height: 1.7;
  color: #555;
}

.article-header__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #888;
}

.article-header__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.article-header__tag {
  display: inline-block;
  padding: 4px 10px;
  font-size: 13px;
  color: #1677ff;
  background: #f0f5ff;
  border-radius: 4px;
  text-decoration: none;
}

.article-header__tag:hover {
  background: #bae0ff;
  text-decoration: none;
}

.article-header__tag--category {
  color: #389e0d;
  background: #f6ffed;
}

.article-header__tag--category:hover {
  background: #d9f7be;
}

.article-header__cover {
  width: 100%;
  max-height: 400px;
  object-fit: cover;
  border-radius: 8px;
  margin-top: 8px;
}

@media (max-width: 480px) {
  .article-header__title {
    font-size: 24px;
  }
}
</style>
