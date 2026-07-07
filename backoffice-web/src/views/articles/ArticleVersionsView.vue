<template>
  <a-card :bordered="false">
    <template #title>版本记录</template>
    <template #extra><a-button @click="router.back()">返回</a-button></template>
    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading">
      <a-table-column title="版本号" data-index="version_no" width="100" />
      <a-table-column title="标题" data-index="title" />
      <a-table-column title="变更说明" data-index="change_note" />
      <a-table-column title="创建人" data-index="created_by_name" width="130" />
      <a-table-column title="创建时间" key="created_at" width="180">
        <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
      </a-table-column>
      <a-table-column title="操作" key="actions" width="140">
        <template #default="{ record }">
          <a-space>
            <a-button size="small" @click="openDetail(record)">详情</a-button>
            <a-button v-if="canRollback" size="small" danger @click="rollback(record.id)">回滚</a-button>
          </a-space>
        </template>
      </a-table-column>
    </a-table>
  </a-card>
  <a-drawer v-model:open="detailOpen" title="版本详情" width="760">
    <pre class="version-content">{{ active?.content }}</pre>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Modal, message } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import { fetchArticleVersions, rollbackArticleVersion, type ArticleVersion } from '../../api/modules/articles';
import { useAuthStore } from '../../stores/auth';
import { formatDateTime } from '../../utils/datetime';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const articleId = Number(route.params.id);
const loading = ref(false);
const rows = ref<ArticleVersion[]>([]);
const detailOpen = ref(false);
const active = ref<ArticleVersion | null>(null);
const canRollback = computed(() => auth.hasPermission('content.version.rollback'));

async function load() {
  loading.value = true;
  try {
    rows.value = (await fetchArticleVersions(articleId)).items;
  } finally {
    loading.value = false;
  }
}
function openDetail(row: ArticleVersion) {
  active.value = row;
  detailOpen.value = true;
}
function rollback(versionId: number) {
  Modal.confirm({
    title: '回滚版本',
    content: '回滚后文章会恢复为草稿，需要重新发布。',
    onOk: async () => {
      await rollbackArticleVersion(articleId, versionId, { comment: '后台回滚' });
      message.success('已回滚');
      await load();
    },
  });
}
onMounted(load);
</script>

<style scoped>
.version-content {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
