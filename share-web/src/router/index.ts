import { createRouter, createWebHistory } from 'vue-router';
import ShareCaseView from '../views/ShareCaseView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: { name: 'share-case', params: { shareCode: 'invalid' } },
    },
    {
      path: '/s/:shareCode',
      name: 'share-case',
      component: ShareCaseView,
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: { name: 'share-case', params: { shareCode: 'invalid' } },
    },
  ],
});

export default router;
