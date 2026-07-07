<template>
  <a-modal v-model:open="open" title="文章分享链接" :footer="null" width="680px">
    <a-spin :spinning="loading">
      <a-descriptions v-if="link" bordered :column="1" size="small">
        <a-descriptions-item label="Web 链接">
          <a-space>
            <a-typography-link :href="link.share_url" target="_blank">{{ link.share_url }}</a-typography-link>
            <a-button size="small" @click="copy(link.share_url)">复制</a-button>
          </a-space>
        </a-descriptions-item>
        <a-descriptions-item label="App Scheme">
          <a-space>
            <span>{{ link.app_scheme_url }}</span>
            <a-button size="small" @click="copy(link.app_scheme_url)">复制</a-button>
          </a-space>
        </a-descriptions-item>
      </a-descriptions>
    </a-spin>
  </a-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { message } from 'ant-design-vue';
import { fetchArticleShareLink, type ArticleShareLink } from '../../api/modules/articles';

const open = ref(false);
const loading = ref(false);
const link = ref<ArticleShareLink | null>(null);

async function show(articleId: number) {
  open.value = true;
  loading.value = true;
  try {
    link.value = await fetchArticleShareLink(articleId);
  } finally {
    loading.value = false;
  }
}

async function copy(text: string) {
  await navigator.clipboard.writeText(text);
  message.success('已复制');
}

defineExpose({ show });
</script>
