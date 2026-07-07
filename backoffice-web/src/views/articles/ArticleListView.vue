<template>
  <a-card :bordered="false" style="margin-bottom: 16px">
    <a-space wrap>
      <a-button v-if="canCreate" type="primary" @click="router.push('/articles/new')">新建文章</a-button>
      <a-input-search v-model:value="query.q" placeholder="标题 / 摘要 / slug" enter-button style="width: 260px" @search="load" />
      <a-select v-model:value="query.status" style="width: 120px" @change="load">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option :value="0">草稿</a-select-option>
        <a-select-option :value="2">已发布</a-select-option>
        <a-select-option :value="3">已下架</a-select-option>
        <a-select-option :value="4">已归档</a-select-option>
      </a-select>
      <a-select v-model:value="query.locale" style="width: 120px" @change="load">
        <a-select-option value="">全部语言</a-select-option>
        <a-select-option value="zh-CN">中文</a-select-option>
        <a-select-option value="en-US">英文</a-select-option>
      </a-select>
      <a-select v-model:value="query.category_id" style="width: 180px" allow-clear placeholder="分类" @change="load">
        <a-select-option v-for="item in flatCategories" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
      </a-select>
      <a-select v-model:value="query.tag_id" style="width: 180px" allow-clear placeholder="标签" @change="load">
        <a-select-option v-for="item in tags" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
      </a-select>
      <a-button :loading="loading" @click="load">刷新</a-button>
    </a-space>
  </a-card>

  <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :scroll="{ x: 1650 }">
    <a-table-column title="标题" key="title" :width="300" fixed="left">
      <template #default="{ record }">
        <a-space direction="vertical" size="small">
          <a-button type="link" style="padding: 0; height: auto" @click="router.push(`/articles/${record.id}/edit`)">{{ record.title }}</a-button>
          <span style="color: #8c8c8c">{{ record.slug }}</span>
        </a-space>
      </template>
    </a-table-column>
    <a-table-column title="语言" data-index="locale" width="95" />
    <a-table-column title="分类" key="category" width="140">
      <template #default="{ record }">{{ record.category?.name || '-' }}</template>
    </a-table-column>
    <a-table-column title="标签" key="tags" width="220">
      <template #default="{ record }">
        <a-space wrap>
          <a-tag v-for="tag in record.tags.slice(0, 3)" :key="tag.id">{{ tag.name }}</a-tag>
        </a-space>
      </template>
    </a-table-column>
    <a-table-column title="状态" key="status" width="100">
      <template #default="{ record }"><ArticleStatusBadge :status="record.status" :label="record.status_label" /></template>
    </a-table-column>
    <a-table-column title="可见性" key="visibility" width="100">
      <template #default="{ record }"><ArticleVisibilityBadge :visibility="record.visibility" :label="record.visibility_label" /></template>
    </a-table-column>
    <a-table-column title="点击量" data-index="view_count" width="100" />
    <a-table-column title="平均阅读" key="avg" width="110">
      <template #default="{ record }">{{ record.average_reading_time_seconds }} 秒</template>
    </a-table-column>
    <a-table-column title="发布时间" key="published_at" width="180">
      <template #default="{ record }">{{ formatDateTime(record.published_at) }}</template>
    </a-table-column>
    <a-table-column title="更新时间" key="updated_at" width="180">
      <template #default="{ record }">{{ formatDateTime(record.updated_at) }}</template>
    </a-table-column>
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" @click="router.push(`/articles/${record.id}/edit`)">编辑</a-button>
          <a-button v-if="canPublish && record.status !== 2" size="small" type="primary" @click="publishRow(record.id)">发布</a-button>
          <a-button v-if="canOffline && record.status === 2" size="small" @click="offlineRow(record.id)">下架</a-button>
          <a-button size="small" @click="shareModal?.show(record.id)">分享</a-button>
          <a-button size="small" @click="router.push(`/articles/${record.id}/versions`)">版本</a-button>
          <a-button v-if="canDelete" size="small" danger @click="deleteRow(record.id)">删除</a-button>
        </TableHoverActions>
      </template>
    </a-table-column>
  </a-table>

  <a-pagination
    style="margin-top: 16px; text-align: right"
    :current="query.page"
    :page-size="query.page_size"
    :total="pagination.total"
    @change="onPageChange"
  />

  <ArticleShareLinkModal ref="shareModal" />
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRouter } from 'vue-router';
import {
  deleteArticle,
  fetchArticleCategories,
  fetchArticles,
  fetchArticleTags,
  offlineArticle,
  publishArticle,
  type ArticleCategory,
  type ArticleRow,
  type ArticleTag,
} from '../../api/modules/articles';
import type { Pagination } from '../../types';
import { useAuthStore } from '../../stores/auth';
import { formatDateTime } from '../../utils/datetime';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';
import TableHoverActions from '../../components/TableHoverActions.vue';
import ArticleShareLinkModal from '../../components/articles/ArticleShareLinkModal.vue';
import ArticleStatusBadge from '../../components/articles/ArticleStatusBadge.vue';
import ArticleVisibilityBadge from '../../components/articles/ArticleVisibilityBadge.vue';

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const rows = ref<ArticleRow[]>([]);
const categories = ref<ArticleCategory[]>([]);
const tags = ref<ArticleTag[]>([]);
const shareModal = ref<InstanceType<typeof ArticleShareLinkModal> | null>(null);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive<Record<string, any>>({ page: 1, page_size: 20, q: '', status: '', locale: '', category_id: undefined, tag_id: undefined });

const canCreate = computed(() => auth.hasPermission('content.article.create'));
const canPublish = computed(() => auth.hasPermission('content.article.publish'));
const canOffline = computed(() => auth.hasPermission('content.article.offline'));
const canDelete = computed(() => auth.hasPermission('content.article.delete'));
const actionsColWidth = computed(() => calcActionsColWidth({ buttons: 6, min: 420, perButton: 62 }));

const flatCategories = computed(() => {
  const result: ArticleCategory[] = [];
  const visit = (items: ArticleCategory[], prefix = '') => {
    items.forEach((item) => {
      result.push({ ...item, name: `${prefix}${item.name}` });
      if (item.children?.length) visit(item.children, `${prefix}${item.name} / `);
    });
  };
  visit(categories.value);
  return result;
});

async function load() {
  loading.value = true;
  try {
    const data = await fetchArticles(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  categories.value = await fetchArticleCategories({ tree: true });
  const tagData = await fetchArticleTags({ page: 1, page_size: 200, is_active: true });
  tags.value = tagData.items;
}

function publishRow(id: number) {
  Modal.confirm({
    title: '发布文章',
    content: '发布后 App 端可读取该文章。',
    onOk: async () => {
      await publishArticle(id, { comment: '后台发布' });
      message.success('已发布');
      await load();
    },
  });
}

function offlineRow(id: number) {
  Modal.confirm({
    title: '下架文章',
    content: '下架后 App 端将不可读取。',
    onOk: async () => {
      await offlineArticle(id, { comment: '后台下架' });
      message.success('已下架');
      await load();
    },
  });
}

function deleteRow(id: number) {
  Modal.confirm({
    title: '删除文章',
    content: '文章将进入回收站。',
    okButtonProps: { danger: true },
    onOk: async () => {
      await deleteArticle(id, { comment: '后台删除' });
      message.success('已删除');
      await load();
    },
  });
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(async () => {
  await loadOptions();
  await load();
});
</script>
