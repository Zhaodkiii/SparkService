<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    message?: string;
    showRetry?: boolean;
    showOpenApp?: boolean;
  }>(),
  {
    title: '页面未找到',
    message: '您访问的页面不存在',
    showRetry: false,
    showOpenApp: true,
  },
);

const emit = defineEmits<{
  retry: [];
  openApp: [];
}>();

const downloadUrl =
  import.meta.env.VITE_APP_DOWNLOAD_URL ||
  'https://apps.apple.com/cn/app/id6751417431';
</script>

<template>
  <div class="public-error" role="alert">
    <div class="public-error__icon" aria-hidden="true">!</div>
    <h1 class="public-error__title">{{ title }}</h1>
    <p class="public-error__message">{{ message }}</p>
    <div class="public-error__actions">
      <button v-if="showRetry" type="button" class="public-error__btn" @click="emit('retry')">
        重试
      </button>
      <a
        v-if="showOpenApp"
        :href="downloadUrl"
        class="public-error__btn public-error__btn--primary"
        target="_blank"
        rel="noopener noreferrer"
      >
        下载 App
      </a>
    </div>
  </div>
</template>

<style scoped>
.public-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 48px 20px;
  text-align: center;
}

.public-error__icon {
  width: 56px;
  height: 56px;
  margin-bottom: 20px;
  font-size: 28px;
  font-weight: 700;
  line-height: 56px;
  color: #1677ff;
  background: #e6f4ff;
  border-radius: 50%;
}

.public-error__title {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 600;
  color: #1a1a1a;
}

.public-error__message {
  margin: 0 0 24px;
  font-size: 15px;
  color: #666;
  max-width: 320px;
}

.public-error__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}

.public-error__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
  padding: 10px 20px;
  font-size: 15px;
  color: #1677ff;
  background: #fff;
  border: 1px solid #1677ff;
  border-radius: 8px;
  text-decoration: none;
}

.public-error__btn:hover {
  background: #f0f5ff;
}

.public-error__btn--primary {
  color: #fff;
  background: #1677ff;
  border-color: #1677ff;
}

.public-error__btn--primary:hover {
  background: #4096ff;
}
</style>
