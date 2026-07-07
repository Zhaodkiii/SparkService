<script setup lang="ts">
defineProps<{
  title: string;
  memberName: string;
  downloadUrl: string;
}>();
</script>

<template>
  <header class="top-bar">
    <div class="brand-mark">S</div>
    <div class="top-copy">
      <p class="eyebrow">Medical Share</p>
      <h1>{{ title }}</h1>
      <p class="subtle">{{ memberName || '公开分享' }}</p>
    </div>
    <a class="download-link" :href="downloadUrl">下载 App</a>
  </header>
</template>
