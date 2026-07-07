<script setup lang="ts">
const emit = defineEmits<{
  openApp: [];
}>();

function handleOpenApp() {
  emit('openApp');
}
</script>

<template>
  <header class="app-banner" role="banner">
    <div class="app-banner__brand">
      <img src="/favicon.svg" alt="" class="app-banner__logo" width="28" height="28" />
      <span class="app-banner__name">小鲸健康</span>
    </div>
    <button
      type="button"
      class="app-banner__cta"
      aria-label="打开小鲸健康 App"
      @click="handleOpenApp"
    >
      打开 App
    </button>
  </header>
</template>

<style scoped>
.app-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  position: sticky;
  top: 0;
  z-index: 50;
}

.app-banner__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.app-banner__logo {
  flex-shrink: 0;
  border-radius: 6px;
}

.app-banner__name {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.app-banner__cta {
  flex-shrink: 0;
  padding: 6px 14px;
  font-size: 14px;
  font-weight: 500;
  color: #1677ff;
  background: #e6f4ff;
  border: none;
  border-radius: 16px;
  white-space: nowrap;
}

.app-banner__cta:hover {
  background: #bae0ff;
}
</style>
