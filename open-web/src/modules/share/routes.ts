import type { RouteRecordRaw } from 'vue-router';

export const shareRoutes: RouteRecordRaw[] = [
  {
    path: '/share/:code',
    name: 'share-landing',
    component: () => import('./views/ShareLandingView.vue'),
    meta: { module: 'share', public: true },
  },
];
