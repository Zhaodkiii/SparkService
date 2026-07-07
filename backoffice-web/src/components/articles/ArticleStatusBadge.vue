<template>
  <a-tag :color="color">{{ label }}</a-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{ status: number; label?: string }>();

const color = computed(() => {
  if (props.status === 2) return 'green';
  if (props.status === 3) return 'orange';
  if (props.status === 4) return 'default';
  return 'blue';
});

const label = computed(() => props.label || ({ 0: '草稿', 2: '已发布', 3: '已下架', 4: '已归档' } as Record<number, string>)[props.status] || String(props.status));
</script>
