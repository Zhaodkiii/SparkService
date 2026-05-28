<template>
  <div
    class="spark-table-hover-actions"
    :class="[`is-align-${align}`, { 'is-hover': mode === 'hover' }]"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 默认一直展示；需要“行 hover 才显示”时再用 hover */
    mode?: 'always' | 'hover';
    /** 默认居中；必要时可用 right/left */
    align?: 'center' | 'left' | 'right';
  }>(),
  {
    mode: 'always',
    align: 'center',
  },
);
</script>
