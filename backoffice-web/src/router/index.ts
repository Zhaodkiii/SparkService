import { createRouter, createWebHistory } from 'vue-router';
import { constantRoutes } from './routes';
import { useAuthStore } from '../stores/auth';

const router = createRouter({
  history: createWebHistory(),
  routes: constantRoutes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  if (to.meta.public) {
    return true;
  }

  if (!auth.isAuthenticated) {
    return '/login';
  }

  if (!auth.user) {
    try {
      await auth.loadProfile();
    } catch {
      auth.logout();
      return '/login';
    }
  }

  return true;
});

export default router;
