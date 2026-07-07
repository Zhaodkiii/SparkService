import http from '../../../shared/api/http';
import type {
  PublicContentArticle,
  PublicContentArticleListResponse,
  PublicContentCategoryNode,
  PublicContentTag,
} from '../types';

export interface ReadEventPayload {
  locale?: string;
  session_id?: string;
  client_platform?: 'web';
}

export interface ReadingDurationPayload extends ReadEventPayload {
  duration_seconds: number;
}

const defaultLocale = import.meta.env.VITE_DEFAULT_LOCALE || 'zh-CN';

export function fetchPublicArticle(slug: string, locale = defaultLocale) {
  return http.get<unknown, PublicContentArticle>(
    `/api/v1/content/articles/${encodeURIComponent(slug)}/`,
    { params: { locale } },
  );
}

export function recordPublicArticleView(articleId: number, payload: ReadEventPayload) {
  return http.post(`/api/v1/content/articles/${articleId}/view/`, payload);
}

export function recordPublicArticleDuration(articleId: number, payload: ReadingDurationPayload) {
  return http.post(`/api/v1/content/articles/${articleId}/reading-duration/`, payload);
}

export function recordPublicArticleDurationBeacon(
  articleId: number,
  payload: ReadingDurationPayload,
): boolean {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '';
  const url = `${baseURL}/api/v1/content/articles/${articleId}/reading-duration/`;
  const body = JSON.stringify(payload);

  if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
    const blob = new Blob([body], { type: 'application/json' });
    if (navigator.sendBeacon(url, blob)) {
      return true;
    }
  }

  if (typeof fetch !== 'undefined') {
    fetch(url, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
    }).catch(() => {
      recordPublicArticleDuration(articleId, payload).catch(() => undefined);
    });
    return true;
  }

  recordPublicArticleDuration(articleId, payload).catch(() => undefined);
  return false;
}

export interface ContentListParams {
  locale?: string;
  page?: number;
  page_size?: number;
  category_id?: number | string;
  tag_id?: number | string;
  q?: string;
}

export function fetchPublicArticleList(params: ContentListParams = {}) {
  return http.get<unknown, PublicContentArticleListResponse>('/api/v1/content/articles/', {
    params: {
      locale: defaultLocale,
      page_size: 20,
      ...params,
    },
  });
}

export function fetchPublicCategories() {
  return http.get<unknown, PublicContentCategoryNode[]>('/api/v1/content/categories/');
}

export function fetchPublicTags(locale = defaultLocale) {
  return http.get<unknown, PublicContentTag[]>('/api/v1/content/tags/', { params: { locale } });
}
