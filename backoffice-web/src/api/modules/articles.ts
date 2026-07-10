import http from '../http';
import type { Pagination } from '../../types';

export interface ArticleCategory {
  id: number;
  name: string;
  slug: string;
  parent_id: number;
  description?: string;
  sort_order: number;
  is_active: boolean;
  children?: ArticleCategory[];
}

export interface ArticleTag {
  id: number;
  name: string;
  slug: string;
  description: string;
  article_count: number;
  is_active: boolean;
}

export interface ArticleRow {
  id: number;
  title: string;
  slug: string;
  locale: string;
  translation_group_id: number | null;
  summary: string;
  cover_image: string;
  category: Pick<ArticleCategory, 'id' | 'name' | 'slug'> | null;
  tags: Array<Pick<ArticleTag, 'id' | 'name' | 'slug'>>;
  status: 0 | 2 | 3 | 4;
  status_label: string;
  visibility: 0 | 1 | 2;
  visibility_label: string;
  is_top: boolean;
  is_recommended: boolean;
  view_count: number;
  read_count: number;
  reading_time_seconds: number;
  average_reading_time_seconds: number;
  author_name: string;
  last_editor_name: string;
  published_at: string | null;
  updated_at: string;
  deleted_at?: string | null;
}

export interface ArticleDetail extends ArticleRow {
  content: string;
  content_format: 'markdown';
  category_id: number | null;
  tag_ids: number[];
  sort_order: number;
  seo_title: string;
  seo_description: string;
  source_url: string;
  references_json: unknown;
  offline_at: string | null;
  created_at: string;
  share_links: ArticleShareLink;
}

export interface ArticleVersion {
  id: number;
  article: number;
  version_no: number;
  title: string;
  summary: string;
  content: string;
  content_format: string;
  metadata_json: Record<string, unknown> | null;
  change_note: string;
  created_by: number;
  created_by_name: string;
  created_at: string;
}

export interface ArticleShareLink {
  share_url: string;
  app_scheme_url: string;
  universal_link_url: string;
  title?: string;
  summary?: string;
  cover_image?: string;
}

export interface PageResponse<T> {
  items: T[];
  pagination: Pagination;
}

export interface ArticleOverview {
  total: number;
  published: number;
  draft: number;
  offline: number;
  archived: number;
  total_views: number;
  total_read_seconds: number;
  missing_reference: number;
  stale_review: number;
  recent_7d_views: number;
  popular_articles: ArticleRow[];
  recent_articles: ArticleRow[];
}

export function fetchArticleOverview() {
  return http.get<unknown, ArticleOverview>('/api/admin/v1/content/overview/');
}

export function exportArticlesSql(params: {
  since?: string;
  until?: string;
  locale?: string;
}) {
  return http.get<unknown, Blob>('/api/admin/v1/content/articles/export-sql/', {
    params,
    responseType: 'blob',
  });
}

export function fetchArticles(params: Record<string, unknown>) {
  return http.get<unknown, PageResponse<ArticleRow>>('/api/admin/v1/content/articles/', { params });
}

export function createArticle(payload: Record<string, unknown>) {
  return http.post<unknown, ArticleDetail>('/api/admin/v1/content/articles/', payload);
}

export function fetchArticle(id: number) {
  return http.get<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/`);
}

export function updateArticle(id: number, payload: Record<string, unknown>) {
  return http.patch<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/`, payload);
}

export function deleteArticle(id: number, payload: { comment?: string }) {
  return http.delete(`/api/admin/v1/content/articles/${id}/`, { data: payload });
}

export function restoreArticle(id: number, payload: { comment?: string }) {
  return http.post<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/restore/`, payload);
}

export function publishArticle(id: number, payload: { comment?: string; published_at?: string | null }) {
  return http.post<unknown, { article: ArticleDetail; version: ArticleVersion }>(`/api/admin/v1/content/articles/${id}/publish/`, payload);
}

export function offlineArticle(id: number, payload: { comment?: string }) {
  return http.post<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/offline/`, payload);
}

export function archiveArticle(id: number, payload: { comment?: string }) {
  return http.post<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/archive/`, payload);
}

export function previewArticle(id: number) {
  return http.get<unknown, ArticleDetail & { markdown: string }>(`/api/admin/v1/content/articles/${id}/preview/`);
}

export function fetchArticleShareLink(id: number) {
  return http.get<unknown, ArticleShareLink>(`/api/admin/v1/content/articles/${id}/share-link/`);
}

export function fetchArticleVersions(id: number) {
  return http.get<unknown, { items: ArticleVersion[] }>(`/api/admin/v1/content/articles/${id}/versions/`);
}

export function rollbackArticleVersion(id: number, versionId: number, payload: { comment?: string }) {
  return http.post<unknown, ArticleDetail>(`/api/admin/v1/content/articles/${id}/versions/${versionId}/rollback/`, payload);
}

export function fetchArticleCategories(params: Record<string, unknown> = { tree: true }) {
  return http.get<unknown, ArticleCategory[]>('/api/admin/v1/content/categories/', { params });
}

export function createArticleCategory(payload: Record<string, unknown>) {
  return http.post<unknown, ArticleCategory>('/api/admin/v1/content/categories/', payload);
}

export function updateArticleCategory(id: number, payload: Record<string, unknown>) {
  return http.patch<unknown, ArticleCategory>(`/api/admin/v1/content/categories/${id}/`, payload);
}

export function deleteArticleCategory(id: number) {
  return http.delete<unknown, ArticleCategory | { deleted: boolean }>(`/api/admin/v1/content/categories/${id}/`);
}

export function fetchArticleTags(params: Record<string, unknown>) {
  return http.get<unknown, PageResponse<ArticleTag>>('/api/admin/v1/content/tags/', { params });
}

export function createArticleTag(payload: Record<string, unknown>) {
  return http.post<unknown, ArticleTag>('/api/admin/v1/content/tags/', payload);
}

export function updateArticleTag(id: number, payload: Record<string, unknown>) {
  return http.patch<unknown, ArticleTag>(`/api/admin/v1/content/tags/${id}/`, payload);
}

export function deleteArticleTag(id: number) {
  return http.delete<unknown, ArticleTag | { deleted: boolean }>(`/api/admin/v1/content/tags/${id}/`);
}

export function mergeArticleTags(payload: { source_tag_id: number; target_tag_id: number }) {
  return http.post<unknown, { source_tag_id: number; target_tag_id: number; moved_article_count: number }>('/api/admin/v1/content/tags/merge/', payload);
}

export function fetchArticleCompliance(params: Record<string, unknown>) {
  return http.get<unknown, PageResponse<ArticleRow>>('/api/admin/v1/content/compliance/', { params });
}

export function fetchArticleAnalytics() {
  return http.get<unknown, { items: ArticleRow[] }>('/api/admin/v1/content/analytics/');
}
