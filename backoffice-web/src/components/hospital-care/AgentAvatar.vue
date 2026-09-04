<template>
  <span class="agent-avatar" :style="{ width: size + 'px', height: size + 'px', fontSize: Math.round(size * 0.42) + 'px' }">
    <img
      v-if="stage === 'remote' && src"
      :src="src"
      :alt="name"
      class="agent-avatar__img"
      @error="stage = 'default'"
    />
    <img
      v-else-if="stage === 'default'"
      :src="DEFAULT_AVATAR"
      :alt="name"
      class="agent-avatar__img"
      @error="stage = 'initial'"
    />
    <span v-else class="agent-avatar__initial">{{ initial }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

/**
 * 统一头像降级状态机（BACKOFFICE-HOSPITAL-AGENT-000002）：
 * remote(agent.avatar_url) → default(统一 AI 默认头像) → initial(名称首字)。
 * avatar_version 变化时重置失败状态重新加载。
 */
const DEFAULT_AVATAR =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><rect width="96" height="96" rx="20" fill="#e6f7fb"/><circle cx="48" cy="40" r="16" fill="#00b7d4"/><rect x="24" y="60" width="48" height="20" rx="10" fill="#00b7d4"/><circle cx="42" cy="38" r="3" fill="#fff"/><circle cx="54" cy="38" r="3" fill="#fff"/></svg>',
  );

const props = withDefaults(
  defineProps<{
    src?: string;
    version?: string;
    name?: string;
    size?: number;
  }>(),
  { src: '', version: '', name: '', size: 40 },
);

const stage = ref<'remote' | 'default' | 'initial'>(props.src ? 'remote' : 'default');

watch(
  () => [props.src, props.version],
  () => {
    stage.value = props.src ? 'remote' : 'default';
  },
);

const initial = computed(() => (props.name || 'AI').trim().slice(0, 1).toUpperCase() || 'AI');
</script>

<style scoped>
.agent-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  overflow: hidden;
  background: #e6f7fb;
  color: #00b7d4;
  font-weight: 600;
  flex: none;
  user-select: none;
}
.agent-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.agent-avatar__initial {
  line-height: 1;
}
</style>
