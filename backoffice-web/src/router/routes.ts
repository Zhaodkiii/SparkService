import type { RouteRecordRaw } from 'vue-router';

export const constantRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../layouts/AdminLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: '/dashboard', name: 'Dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: '仪表盘' } },
      { path: '/tasks', name: 'Tasks', component: () => import('../views/TasksDashboardView.vue'), meta: { title: '异步任务看板' } },
      { path: '/users', name: 'Users', component: () => import('../views/UsersView.vue'), meta: { title: '用户管理' } },
      {
        path: '/ai-config/scenarios/:scenarioKey',
        name: 'AIScenarioModels',
        component: () => import('../views/AIScenarioModelsView.vue'),
        meta: { title: '场景模型' },
      },
      { path: '/ai-config/scenarios', name: 'AIScenarios', component: () => import('../views/AIScenariosView.vue'), meta: { title: 'AI场景配置' } },
      { path: '/ai-config/models', name: 'AIModels', component: () => import('../views/AIModelsView.vue'), meta: { title: '模型目录' } },
      { path: '/ai-config/providers', name: 'AIProviders', component: () => import('../views/AIProvidersView.vue'), meta: { title: 'Provider配置' } },
      { path: '/ai-config/trials', name: 'AITrials', component: () => import('../views/AITrialsView.vue'), meta: { title: '试用期' } },
      { path: '/rbac', name: 'RBAC', component: () => import('../views/RBACView.vue'), meta: { title: '权限管理' } },
      { path: '/audit', name: 'Audit', component: () => import('../views/AuditView.vue'), meta: { title: '审计日志' } },
    ],
  },
];
