<template>
  <a-tooltip :title="tooltip">
    <a-button type="text" size="small" class="copy-btn" @click="onCopy">
      <CopyOutlined />
    </a-button>
  </a-tooltip>
</template>

<script setup lang="ts">
import { CopyOutlined } from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import { copyText } from '../../utils/clipboard';

const props = defineProps<{
  value: string | number | null | undefined;
  tooltip?: string;
  successText?: string;
}>();

async function onCopy() {
  const ok = await copyText(String(props.value ?? ''));
  if (ok) {
    message.success(props.successText || '已复制');
  } else {
    message.error('复制失败');
  }
}
</script>

<style scoped>
.copy-btn {
  padding: 0 4px;
}
</style>
