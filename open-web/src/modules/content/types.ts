export interface PublicContentReference {
  title: string;
  url: string | null;
  source: string | null;
  published_at: string | null;
}

export interface PublicContentCategory {
  id: number;
  name: string;
  slug: string;
}

export interface PublicContentTag {
  id: number;
  name: string;
  slug: string;
}

export interface PublicContentArticleListItem {
  id: number;
  title: string;
  slug: string;
  locale: string;
  summary: string;
  cover_image: string | null;
  category: PublicContentCategory | null;
  tags: PublicContentTag[];
  published_at: string | null;
  estimated_reading_minutes: number;
}

export interface PublicContentPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PublicContentArticleListResponse {
  items: PublicContentArticleListItem[];
  pagination: PublicContentPagination;
}

export interface PublicContentCategoryNode extends PublicContentCategory {
  parent_id: number | null;
  children: PublicContentCategoryNode[];
}

export interface PublicContentShareLinks {
  share_url: string;
  app_scheme_url: string;
  universal_link_url: string;
}

export interface PublicContentArticle {
  id: number;
  title: string;
  slug: string;
  locale: string;
  summary: string;
  cover_image: string;
  category: PublicContentCategory | null;
  tags: PublicContentTag[];
  published_at: string | null;
  estimated_reading_minutes: number;
  content: string;
  content_format: 'markdown';
  source_url: string;
  references: PublicContentReference[];
  references_json: PublicContentReference[];
  seo_title: string;
  seo_description: string;
  share_links: PublicContentShareLinks;
  share_url: string;
}

export type ContentErrorKind = 'loading' | 'not_found' | 'unavailable' | 'network' | 'success';
