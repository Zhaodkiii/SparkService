<template>
  <a-tag :color="color">{{ label }}</a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ visibility: number; label?: string }>();

const color = computed(() => {
  if (props.visibility === 1) return 'green';
  if (props.visibility === 2) return 'blue';
  return 'default';
});

const label = computed(() => props.label || ({ 0: '私密', 1: '公开', 2: '未列出' } as Record<number, string>)[props.visibility] || String(props.visibility));
</script>
