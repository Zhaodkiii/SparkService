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

  if(to.meta.paymentAccess&&!['view_paymentattempt','query_payment','refund_order','change_paymentchannel'].some(p=>auth.hasPermission('print_orders.'+p))) return '/dashboard';
  if (to.meta.superAdminOnly && !auth.user?.is_superuser) {
    return '/dashboard';
  }
  if (typeof to.meta.requiredPermission === 'string' && !auth.hasPermission(to.meta.requiredPermission)) {
    return '/dashboard';
  }

  return true;
});

export default router;
