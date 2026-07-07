import { createRouter, createWebHistory } from 'vue-router';
import { contentRoutes } from '../modules/content/routes';
import { shareRoutes } from '../modules/share/routes';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...contentRoutes,
    ...shareRoutes,
    {
      path: '/',
      redirect: () => ({ name: 'not-found' }),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../shared/components/PublicErrorState.vue'),
      meta: { public: true },
    },
  ],
});

export default router;
