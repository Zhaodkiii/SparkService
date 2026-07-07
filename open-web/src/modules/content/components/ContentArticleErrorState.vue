<script setup lang="ts">
import type { ContentErrorKind } from '../types';

const props = defineProps<{
  kind: ContentErrorKind;
}>();

const emit = defineEmits<{
  retry: [];
}>();

const config = {
  loading: {
    title: '',
    message: '正在加载内容...',
    showRetry: false,
  },
  not_found: {
    title: '内容不存在',
    message: '内容不存在或链接已失效',
    showRetry: true,
  },
  unavailable: {
    title: '无法访问',
    message: '内容暂时无法访问',
    showRetry: true,
  },
  network: {
    title: '网络异常',
    message: '网络连接异常，请稍后重试',
    showRetry: true,
  },
  success: {
    title: '',
    message: '',
    showRetry: false,
  },
} as const;

const state = () => config[props.kind] ?? config.network;
</script>

<template>
  <div v-if="kind === 'loading'" class="article-loading" role="status" aria-live="polite">
    <div class="article-loading__spinner" aria-hidden="true" />
    <p>{{ state().message }}</p>
  </div>
  <div v-else class="article-error">
    <div class="article-error__icon" aria-hidden="true">!</div>
    <h1 class="article-error__title">{{ state().title }}</h1>
    <p class="article-error__message">{{ state().message }}</p>
    <button
      v-if="state().showRetry"
      type="button"
      class="article-error__retry"
      @click="emit('retry')"
    >
      重试
    </button>
  </div>
</template>

<style scoped>
.article-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  color: #666;
  font-size: 15px;
}

.article-loading__spinner {
  width: 32px;
  height: 32px;
  margin-bottom: 16px;
  border: 3px solid #e8e8e8;
  border-top-color: #1677ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.article-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  padding: 48px 20px;
  text-align: center;
}

.article-error__icon {
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

.article-error__title {
  margin: 0 0 12px;
  font-size: 22px;
  font-weight: 600;
}

.article-error__message {
  margin: 0 0 24px;
  font-size: 15px;
  color: #666;
}

.article-error__retry {
  padding: 10px 28px;
  font-size: 15px;
  color: #fff;
  background: #1677ff;
  border: none;
  border-radius: 8px;
}

.article-error__retry:hover {
  background: #4096ff;
}
</style>
