<script setup lang="ts">
defineProps<{
  shareUrl: string;
  title: string;
  summary?: string;
  appSchemeUrl?: string;
}>();

const emit = defineEmits<{
  share: [];
  openApp: [];
}>();
</script>

<template>
  <div class="share-bar" role="toolbar" aria-label="分享与操作">
    <button type="button" class="share-bar__btn" aria-label="分享文章" @click="emit('share')">
      <span class="share-bar__icon" aria-hidden="true">↗</span>
      分享
    </button>
    <button
      v-if="appSchemeUrl"
      type="button"
      class="share-bar__btn share-bar__btn--primary"
      aria-label="打开小鲸健康 App"
      @click="emit('openApp')"
    >
      打开 App
    </button>
  </div>
</template>

<style scoped>
.share-bar {
  display: flex;
  gap: 12px;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.share-bar__btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  font-size: 15px;
  font-weight: 500;
  color: #1677ff;
  background: #fff;
  border: 1px solid #1677ff;
  border-radius: 8px;
}

.share-bar__btn:hover {
  background: #f0f5ff;
}

.share-bar__btn--primary {
  color: #fff;
  background: #1677ff;
  border-color: #1677ff;
}

.share-bar__btn--primary:hover {
  background: #4096ff;
}

.share-bar__icon {
  font-size: 16px;
}
</style>
