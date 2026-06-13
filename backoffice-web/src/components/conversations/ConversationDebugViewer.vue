<template>
  <a-modal
    v-model:open="visible"
    :title="title"
    :width="modalWidth"
    :footer="null"
    destroy-on-close
  >
    <div class="debug-toolbar">
      <a-button size="small" :disabled="loading || !data" @click="onCopy">复制调试数据</a-button>
      <a-button v-if="loadError" size="small" type="primary" ghost @click="emit('retry')">重试</a-button>
    </div>
    <div v-if="loading" class="debug-loading">
      <a-spin tip="加载调试数据中..." />
    </div>
    <a-alert v-else-if="loadError" type="error" show-icon :message="loadError" />
    <pre v-else class="debug-body"><code>{{ text }}</code></pre>
  </a-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { message } from 'ant-design-vue';
import { formatJson } from '../../utils/conversationRender';
import { copyText } from '../../utils/clipboard';

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    data: unknown;
    width?: string | number;
    loading?: boolean;
    loadError?: string;
  }>(),
  {
    title: '查看调试数据',
    width: '80vw',
    loading: false,
    loadError: '',
  },
);

const emit = defineEmits<{ 'update:open': [value: boolean]; retry: [] }>();

const visible = computed({
  get: () => props.open,
  set: (value: boolean) => emit('update:open', value),
});

const text = computed(() => (props.data == null ? '' : formatJson(props.data)));
const modalWidth = computed(() => props.width);

async function onCopy() {
  if (!text.value) return;
  const ok = await copyText(text.value);
  if (ok) {
    message.success('调试数据已复制');
  } else {
    message.error('复制失败');
  }
}
</script>

<style scoped>
.debug-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 8px;
}
.debug-loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.debug-body {
  margin: 0;
  max-height: 70vh;
  overflow: auto;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
