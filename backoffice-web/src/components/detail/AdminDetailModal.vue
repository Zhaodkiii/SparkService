<script setup lang="ts">
// 后台详情弹窗统一使用 AdminDetailModal；
// 新增详情弹窗优先复用该组件，避免各页面重复维护 modal/spin/footer/width 等结构。
defineProps<{
  title: string;
  loading?: boolean;
  width?: string;
}>();

const open = defineModel<boolean>('open', { required: true });
</script>

<template>
  <a-modal v-model:open="open" :title="title" :footer="null" :width="width ?? '960px'">
    <a-spin :spinning="loading ?? false">
      <slot />
    </a-spin>
  </a-modal>
</template>
