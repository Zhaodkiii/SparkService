<template>
  <a-space direction="vertical" style="width: 100%">
    <a-input v-model:value="sourceUrl" placeholder="来源链接，例如权威指南、期刊或政策页面" @change="emitChange" />
    <a-textarea v-model:value="referencesText" :rows="5" placeholder='参考文献 JSON，例如 [{"title":"指南名称","url":"https://..."}]' @change="emitChange" />
  </a-space>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

const props = defineProps<{ sourceUrl?: string; referencesJson?: unknown }>();
const emit = defineEmits<{ change: [payload: { source_url: string; references_json: unknown }] }>();

const sourceUrl = ref('');
const referencesText = ref('');

watch(
  () => [props.sourceUrl, props.referencesJson] as const,
  ([url, refs]) => {
    sourceUrl.value = url || '';
    referencesText.value = refs ? JSON.stringify(refs, null, 2) : '';
  },
  { immediate: true },
);

function emitChange() {
  let parsed: unknown = null;
  if (referencesText.value.trim()) {
    try {
      parsed = JSON.parse(referencesText.value);
    } catch {
      const text = referencesText.value.trim();
      parsed = text.toLowerCase().startsWith('http://') || text.toLowerCase().startsWith('https://')
        ? [{ title: text, url: text }]
        : text;
    }
  }
  emit('change', { source_url: sourceUrl.value, references_json: parsed });
}
</script>
