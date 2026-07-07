<script setup lang="ts">
import { computed } from 'vue';
import type { PublicContentReference } from '../types';
import { formatDate } from '../../../shared/utils/datetime';

const props = defineProps<{
  references: PublicContentReference[];
  sourceUrl?: string;
}>();

const displayItems = computed(() => {
  const items = [...(props.references || [])];
  const sourceUrl = (props.sourceUrl || '').trim();
  if (sourceUrl && !items.some((r) => r.url === sourceUrl)) {
    items.push({
      title: sourceUrl,
      url: sourceUrl,
      source: null,
      published_at: null,
    });
  }
  return items.filter((r) => r.title || r.url);
});
</script>

<template>
  <section v-if="displayItems.length" class="references" aria-labelledby="references-heading">
    <h2 id="references-heading" class="references__title">参考来源</h2>
    <ol class="references__list">
      <li v-for="(ref, index) in displayItems" :key="index" class="references__item">
        <a
          v-if="ref.url"
          :href="ref.url"
          class="references__link"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ ref.title || ref.url }}
        </a>
        <span v-else class="references__text">{{ ref.title }}</span>
        <span v-if="ref.source" class="references__source">（{{ ref.source }}）</span>
        <time v-if="ref.published_at" class="references__date" :datetime="ref.published_at">
          {{ formatDate(ref.published_at) }}
        </time>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.references {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.references__title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.references__list {
  margin: 0;
  padding-left: 1.25em;
}

.references__item {
  margin: 10px 0;
  font-size: 15px;
  line-height: 1.7;
  color: #444;
}

.references__link {
  color: #1677ff;
  word-break: break-all;
}

.references__source,
.references__date {
  margin-left: 4px;
  font-size: 13px;
  color: #999;
}
</style>
