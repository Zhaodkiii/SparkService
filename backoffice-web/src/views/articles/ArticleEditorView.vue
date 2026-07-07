<template>
  <a-spin :spinning="loading">
    <a-form layout="vertical">
      <a-card :bordered="false" style="margin-bottom: 16px">
        <template #title>{{ isCreate ? '新建文章' : '编辑文章' }}</template>
        <template #extra>
          <a-space>
            <a-button @click="router.push('/articles/list')">返回</a-button>
            <a-button :loading="saving" @click="submit">保存草稿</a-button>
            <a-button v-if="!isCreate && canPublish" type="primary" :loading="publishing" @click="publishCurrent">发布</a-button>
          </a-space>
        </template>
        <a-row :gutter="16">
          <a-col :xs="24" :lg="16">
            <a-form-item label="标题"><a-input v-model:value="form.title" placeholder="文章标题" /></a-form-item>
          </a-col>
          <a-col :xs="24" :lg="8">
            <a-form-item label="语言">
              <a-select v-model:value="form.locale">
                <a-select-option value="zh-CN">中文 zh-CN</a-select-option>
                <a-select-option value="en-US">英文 en-US</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col v-if="!isCreate" :xs="24" :lg="12">
            <a-form-item label="URL 随机码"><a-input :value="form.slug" disabled /></a-form-item>
          </a-col>
          <a-col :xs="24" :lg="isCreate ? 24 : 12"><a-form-item label="封面图"><a-input v-model:value="form.cover_image" placeholder="https://..." /></a-form-item></a-col>
        </a-row>
        <a-form-item label="摘要"><a-textarea v-model:value="form.summary" :rows="3" /></a-form-item>
      </a-card>

      <a-row :gutter="16">
        <a-col :xs="24" :xl="16">
          <a-card title="Markdown 正文" :bordered="false">
            <a-textarea v-model:value="form.content" :rows="24" placeholder="# 标题&#10;&#10;正文内容" />
          </a-card>
        </a-col>
        <a-col :xs="24" :xl="8">
          <a-card title="发布设置" :bordered="false" style="margin-bottom: 16px">
            <a-form-item label="分类">
              <a-select v-model:value="form.category_id" allow-clear placeholder="选择分类">
                <a-select-option v-for="item in flatCategories" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="标签">
              <a-select v-model:value="form.tag_ids" mode="multiple" placeholder="选择标签">
                <a-select-option v-for="item in tags" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
              </a-select>
            </a-form-item>
            <a-row :gutter="12">
              <a-col :span="12"><a-form-item label="可见性"><a-select v-model:value="form.visibility" :options="visibilityOptions" /></a-form-item></a-col>
              <a-col :span="12"><a-form-item label="排序"><a-input-number v-model:value="form.sort_order" style="width: 100%" /></a-form-item></a-col>
            </a-row>
            <a-space>
              <a-checkbox v-model:checked="form.is_top">置顶</a-checkbox>
              <a-checkbox v-model:checked="form.is_recommended">推荐</a-checkbox>
            </a-space>
          </a-card>

          <a-card title="来源合规" :bordered="false">
            <ArticleReferenceEditor
              :source-url="form.source_url"
              :references-json="form.references_json"
              @change="(v) => Object.assign(form, v)"
            />
            <a-alert style="margin-top: 12px" type="info" show-icon message="医疗健康内容发布前必须填写来源链接或参考文献。" />
          </a-card>
        </a-col>
      </a-row>
    </a-form>
  </a-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { message, Modal } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';
import {
  createArticle,
  fetchArticle,
  fetchArticleCategories,
  fetchArticleTags,
  publishArticle,
  updateArticle,
  type ArticleCategory,
  type ArticleTag,
} from '../../api/modules/articles';
import { useAuthStore } from '../../stores/auth';
import ArticleReferenceEditor from '../../components/articles/ArticleReferenceEditor.vue';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const categories = ref<ArticleCategory[]>([]);
const tags = ref<ArticleTag[]>([]);
const articleId = computed(() => Number(route.params.id || 0));
const isCreate = computed(() => !articleId.value);
const canPublish = computed(() => auth.hasPermission('content.article.publish'));

const form = reactive<Record<string, any>>({
  title: '',
  locale: 'zh-CN',
  summary: '',
  cover_image: '',
  content: '',
  content_format: 'markdown',
  category_id: null,
  tag_ids: [],
  visibility: 1,
  is_top: false,
  is_recommended: false,
  sort_order: 0,
  seo_title: '',
  seo_description: '',
  source_url: '',
  references_json: null,
});

const visibilityOptions = [
  { value: 1, label: '公开' },
  { value: 2, label: '未列出' },
  { value: 0, label: '私密' },
];

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

async function loadOptions() {
  categories.value = await fetchArticleCategories({ tree: true });
  tags.value = (await fetchArticleTags({ page: 1, page_size: 200, is_active: true })).items;
}

async function loadArticle() {
  if (isCreate.value) return;
  loading.value = true;
  try {
    const data = await fetchArticle(articleId.value);
    Object.assign(form, data);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  saving.value = true;
  try {
    if (isCreate.value) {
      const created = await createArticle(form);
      message.success('已创建文章');
      router.replace(`/articles/${created.id}/edit`);
    } else {
      await updateArticle(articleId.value, form);
      message.success('已保存');
      await loadArticle();
    }
  } catch (error: any) {
    message.error(error?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

function publishCurrent() {
  Modal.confirm({
    title: '发布文章',
    content: '发布前会校验来源链接或参考文献。',
    onOk: async () => {
      publishing.value = true;
      try {
        await publishArticle(articleId.value, { comment: '后台发布' });
        message.success('已发布');
        await loadArticle();
      } finally {
        publishing.value = false;
      }
    },
  });
}

onMounted(async () => {
  await loadOptions();
  await loadArticle();
});
</script>
