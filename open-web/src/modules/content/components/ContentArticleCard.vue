<script setup lang="ts">
import { RouterLink } from 'vue-router';
import { formatDate } from '../../../shared/utils/datetime';
import type { PublicContentArticleListItem } from '../types';

defineProps<{
  article: PublicContentArticleListItem;
}>();

const emit = defineEmits<{
  categoryClick: [categoryId: number];
  tagClick: [tagId: number];
}>();
</script>

<template>
  <article class="article-card" role="article" :aria-label="article.title">
    <RouterLink
      :to="{ name: 'content-article-detail', params: { slug: article.slug } }"
      class="article-card__link"
    >
      <img
        v-if="article.cover_image"
        :src="article.cover_image"
        :alt="article.title"
        class="article-card__cover"
        loading="lazy"
      />
      <div v-else class="article-card__cover article-card__cover--placeholder" aria-hidden="true" />

      <div class="article-card__body">
        <button
          v-if="article.category"
          type="button"
          class="article-card__badge article-card__badge--category"
          @click.prevent.stop="emit('categoryClick', article.category!.id)"
        >
          {{ article.category.name }}
        </button>

        <h2 class="article-card__title">{{ article.title }}</h2>

        <p v-if="article.summary" class="article-card__summary">{{ article.summary }}</p>

        <div class="article-card__footer">
          <div v-if="article.tags.length" class="article-card__tags">
            <button
              v-for="tag in article.tags"
              :key="tag.id"
              type="button"
              class="article-card__tag"
              @click.prevent.stop="emit('tagClick', tag.id)"
            >
              {{ tag.name }}
            </button>
          </div>
          <div class="article-card__meta">
            <span v-if="article.estimated_reading_minutes">
              {{ article.estimated_reading_minutes }} 分钟
            </span>
            <span v-if="article.published_at && article.estimated_reading_minutes"> · </span>
            <time v-if="article.published_at" :datetime="article.published_at">
              {{ formatDate(article.published_at) }}
            </time>
          </div>
        </div>
      </div>
    </RouterLink>
  </article>
</template>

<style scoped>
.article-card {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.article-card__link {
  display: block;
  color: inherit;
  text-decoration: none;
}

.article-card__link:hover .article-card__title {
  color: #1677ff;
}

.article-card__cover {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
}

.article-card__cover--placeholder {
  background: linear-gradient(135deg, #f0f5ff 0%, #e6f4ff 100%);
}

.article-card__body {
  padding: 14px 16px 16px;
}

.article-card__badge {
  display: inline-block;
  margin-bottom: 8px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.article-card__badge--category {
  color: #389e0d;
  background: #f6ffed;
}

.article-card__badge--category:hover {
  background: #d9f7be;
}

.article-card__title {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.4;
  color: #111;
  transition: color 0.15s;
}

.article-card__summary {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.article-card__footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.article-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.article-card__tag {
  padding: 2px 8px;
  font-size: 12px;
  color: #1677ff;
  background: #f0f5ff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.article-card__tag:hover {
  background: #bae0ff;
}

.article-card__meta {
  font-size: 12px;
  color: #888;
}
</style>
