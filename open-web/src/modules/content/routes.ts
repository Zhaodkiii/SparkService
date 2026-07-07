import type { RouteRecordRaw } from 'vue-router';

export const contentRoutes: RouteRecordRaw[] = [
  {
    path: '/content',
    name: 'content-article-list',
    component: () => import('./views/ContentArticleListView.vue'),
    meta: { module: 'content', public: true },
  },
  {
    path: '/content/:slug',
    name: 'content-article-detail',
    component: () => import('./views/ContentArticleDetailView.vue'),
    meta: { module: 'content', public: true },
  },
];
