<script setup lang="ts">
import type { ShareErrorKind } from '../types';

defineProps<{
  kind: ShareErrorKind;
  title?: string;
  description?: string;
}>();

const emit = defineEmits<{
  download: [];
}>();
</script>

<template>
  <section v-if="kind === 'loading'" class="state-card" role="status" aria-live="polite">
    <div class="spinner" aria-hidden="true" />
    <h2>正在加载分享内容</h2>
    <p>请稍候，我们正在获取公开分享内容。</p>
  </section>

  <section v-else class="state-card expired" role="alert">
    <div class="state-badge">已失效</div>
    <h2>{{ title || '链接已失效' }}</h2>
    <p>{{ description || '请下载 App 继续查看完整医疗档案。' }}</p>
    <button class="primary-button" type="button" @click="emit('download')">下载 App</button>
  </section>
</template>
