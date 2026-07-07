<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import AppOpenBanner from '../../../shared/components/AppOpenBanner.vue';
import PublicPageShell from '../../../shared/components/PublicPageShell.vue';
import { useDocumentMeta } from '../../../shared/composables/useDocumentMeta';
import { usePublicShare } from '../../../shared/composables/usePublicShare';
import { useReadingDuration } from '../../../shared/composables/useReadingDuration';
import { useSessionId } from '../../../shared/composables/useSessionId';
import { fetchPublicArticle, recordPublicArticleView } from '../api/contentApi';
import ContentArticleErrorState from '../components/ContentArticleErrorState.vue';
import ContentArticleHeader from '../components/ContentArticleHeader.vue';
import ContentArticleMarkdown from '../components/ContentArticleMarkdown.vue';
import ContentArticleReferences from '../components/ContentArticleReferences.vue';
import ContentArticleShareBar from '../components/ContentArticleShareBar.vue';
import type { ContentErrorKind, PublicContentArticle } from '../types';

const VIEWED_KEY = 'open_web_content_viewed';

const route = useRoute();
const sessionId = useSessionId();
const { updateMeta } = useDocumentMeta();
const { toast, shareOrCopy, openApp } = usePublicShare();

const article = ref<PublicContentArticle | null>(null);
const errorKind = ref<ContentErrorKind>('loading');
const showBackToTop = ref(false);

const defaultLocale = import.meta.env.VITE_DEFAULT_LOCALE || 'zh-CN';

const locale = computed(() => {
  const q = route.query.locale;
  return typeof q === 'string' && q ? q : defaultLocale;
});

const slug = computed(() => String(route.params.slug || ''));

function classifyError(err: unknown): ContentErrorKind {
  const message = err instanceof Error ? err.message : '';
  if (message === 'not_found') return 'not_found';
  if (message.includes('Network Error') || message === 'request_failed') return 'network';
  return 'unavailable';
}

function getViewedIds(): number[] {
  try {
    const raw = sessionStorage.getItem(VIEWED_KEY);
    return raw ? (JSON.parse(raw) as number[]) : [];
  } catch {
    return [];
  }
}

function markViewed(articleId: number) {
  const ids = getViewedIds();
  if (!ids.includes(articleId)) {
    ids.push(articleId);
    sessionStorage.setItem(VIEWED_KEY, JSON.stringify(ids));
  }
}

function hasViewed(articleId: number): boolean {
  return getViewedIds().includes(articleId);
}

async function trackView(data: PublicContentArticle) {
  if (hasViewed(data.id)) return;
  try {
    await recordPublicArticleView(data.id, {
      locale: data.locale,
      session_id: sessionId,
      client_platform: 'web',
    });
    markViewed(data.id);
  } catch {
    // non-blocking
  }
}

async function loadArticle() {
  if (!slug.value) {
    errorKind.value = 'not_found';
    article.value = null;
    return;
  }

  errorKind.value = 'loading';
  article.value = null;

  try {
    const data = await fetchPublicArticle(slug.value, locale.value);
    article.value = data;
    errorKind.value = 'success';

    updateMeta({
      title: data.seo_title || data.title,
      description: data.seo_description || data.summary,
      image: data.cover_image || undefined,
      url: typeof window !== 'undefined' ? window.location.href : undefined,
      publishedAt: data.published_at,
    });

    await trackView(data);
  } catch (err) {
    article.value = null;
    errorKind.value = classifyError(err);
  }
}

useReadingDuration({
  articleId: () => article.value?.id ?? null,
  locale: () => locale.value,
  sessionId,
});

function handleShare() {
  if (!article.value) return;
  const url = article.value.share_url || window.location.href;
  shareOrCopy({
    title: article.value.title,
    text: article.value.summary,
    url,
  });
}

function handleOpenApp() {
  const scheme = article.value?.share_links?.app_scheme_url;
  openApp(scheme);
}

function onScroll() {
  showBackToTop.value = window.scrollY > 400;
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

watch([slug, locale], () => {
  loadArticle();
});

onMounted(() => {
  loadArticle();
  window.addEventListener('scroll', onScroll, { passive: true });
});

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll);
});
</script>

<template>
  <PublicPageShell>
    <template #banner>
      <AppOpenBanner @open-app="handleOpenApp" />
    </template>

    <ContentArticleErrorState
      v-if="errorKind !== 'success'"
      :kind="errorKind"
      @retry="loadArticle"
    />

    <article v-else-if="article">
      <ContentArticleHeader :article="article" />
      <ContentArticleMarkdown :content="article.content" />
      <ContentArticleReferences
        :references="article.references"
        :source-url="article.source_url"
      />
      <p class="public-page__disclaimer">
        本文为健康科普内容，不能替代医生诊断、治疗建议或用药指导。如有不适，请及时咨询专业医生。
      </p>
      <ContentArticleShareBar
        :share-url="article.share_url"
        :title="article.title"
        :summary="article.summary"
        :app-scheme-url="article.share_links?.app_scheme_url"
        @share="handleShare"
        @open-app="handleOpenApp"
      />
    </article>

    <button
      v-if="errorKind === 'success'"
      type="button"
      class="back-to-top"
      :hidden="!showBackToTop"
      aria-label="回到顶部"
      @click="scrollToTop"
    >
      ↑
    </button>

    <div v-if="toast" class="public-toast" role="status">{{ toast }}</div>
  </PublicPageShell>
</template>
