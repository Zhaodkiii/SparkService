<script setup lang="ts">
import type { PublicContentCategoryNode } from '../types';

const props = defineProps<{
  categories: PublicContentCategoryNode[];
  modelValue: number | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
}>();

function selectCategory(id: number | null) {
  if (props.modelValue === id) return;
  emit('update:modelValue', id);
}
</script>

<template>
  <div class="category-tabs" role="tablist" aria-label="文章分类">
    <button
      type="button"
      role="tab"
      class="category-tabs__tab"
      :class="{ 'category-tabs__tab--active': modelValue === null }"
      :aria-selected="modelValue === null"
      @click="selectCategory(null)"
    >
      全部
    </button>
    <button
      v-for="category in categories"
      :key="category.id"
      type="button"
      role="tab"
      class="category-tabs__tab"
      :class="{ 'category-tabs__tab--active': modelValue === category.id }"
      :aria-selected="modelValue === category.id"
      @click="selectCategory(category.id)"
    >
      {{ category.name }}
    </button>
  </div>
</template>

<style scoped>
.category-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 0;
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}

.category-tabs::-webkit-scrollbar {
  display: none;
}

.category-tabs__tab {
  flex-shrink: 0;
  padding: 6px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #555;
  background: #f5f5f5;
  border: none;
  border-radius: 20px;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.category-tabs__tab:hover {
  background: #e6f4ff;
  color: #1677ff;
}

.category-tabs__tab--active {
  color: #fff;
  background: #1677ff;
}

.category-tabs__tab--active:hover {
  background: #4096ff;
  color: #fff;
}
</style>
