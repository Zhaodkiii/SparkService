<script setup lang="ts">
import type { PublicContentTag } from '../types';

const props = defineProps<{
  tags: PublicContentTag[];
  modelValue: number | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
}>();

function selectTag(id: number | null) {
  if (props.modelValue === id) return;
  emit('update:modelValue', id);
}
</script>

<template>
  <div v-if="tags.length" class="tag-filter" role="group" aria-label="标签筛选">
    <button
      type="button"
      class="tag-filter__chip"
      :class="{ 'tag-filter__chip--active': modelValue === null }"
      :aria-pressed="modelValue === null"
      @click="selectTag(null)"
    >
      全部标签
    </button>
    <button
      v-for="tag in tags"
      :key="tag.id"
      type="button"
      class="tag-filter__chip"
      :class="{ 'tag-filter__chip--active': modelValue === tag.id }"
      :aria-pressed="modelValue === tag.id"
      @click="selectTag(tag.id)"
    >
      {{ tag.name }}
    </button>
  </div>
</template>

<style scoped>
.tag-filter {
  display: flex;
  gap: 8px;
  padding: 0 0 12px;
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}

.tag-filter::-webkit-scrollbar {
  display: none;
}

.tag-filter__chip {
  flex-shrink: 0;
  padding: 4px 12px;
  font-size: 13px;
  color: #1677ff;
  background: #f0f5ff;
  border: 1px solid transparent;
  border-radius: 16px;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.tag-filter__chip:hover {
  background: #bae0ff;
}

.tag-filter__chip--active {
  color: #fff;
  background: #1677ff;
  border-color: #1677ff;
}

.tag-filter__chip--active:hover {
  background: #4096ff;
}
</style>
