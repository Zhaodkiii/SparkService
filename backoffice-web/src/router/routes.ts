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
      { path: '/tasks/manager', name: 'TasksManager', component: () => import('../views/TasksManagerView.vue'), meta: { title: '异步任务管理' } },
      { path: '/users', name: 'Users', component: () => import('../views/UsersView.vue'), meta: { title: '用户管理' } },
      { path: '/users/devices', name: 'Devices', component: () => import('../views/DevicesView.vue'), meta: { title: '设备管理' } },
      { path: '/users/deactivations', name: 'Deactivations', component: () => import('../views/DeactivationsView.vue'), meta: { title: '注销管理' } },
      { path: '/notifications/users', name: 'NotificationUsers', component: () => import('../views/NotificationUsersView.vue'), meta: { title: '通知用户列表' } },
      { path: '/notifications/templates', name: 'NotificationTemplates', component: () => import('../views/NotificationTemplatesView.vue'), meta: { title: '通知模板' } },
      { path: '/notifications/campaigns', name: 'NotificationCampaigns', component: () => import('../views/NotificationCampaignsView.vue'), meta: { title: '发送活动' } },
      { path: '/notifications/apns', name: 'NotificationAPNs', component: () => import('../views/NotificationAPNsView.vue'), meta: { title: 'APNs发送记录', channel: 'apns' } },
      { path: '/notifications/sms', name: 'NotificationSMS', component: () => import('../views/NotificationSMSView.vue'), meta: { title: '短信发送记录', channel: 'sms' } },
      { path: '/notifications/email', name: 'NotificationEmail', component: () => import('../views/NotificationEmailView.vue'), meta: { title: '邮箱发送记录', channel: 'email' } },
      { path: '/version/configs', name: 'VersionConfigs', component: () => import('../views/VersionConfigsView.vue'), meta: { title: '版本配置' } },
      { path: '/version/logs', name: 'VersionLogs', component: () => import('../views/VersionLogsView.vue'), meta: { title: '检查日志' } },
      {
        path: '/ai-config/scenarios/:scenarioKey',
        name: 'AIScenarioModels',
        component: () => import('../views/AIScenarioModelsView.vue'),
        meta: { title: '场景模型' },
      },
      { path: '/ai-config/scenarios', name: 'AIScenarios', component: () => import('../views/AIScenariosView.vue'), meta: { title: 'AI场景配置' } },
      { path: '/ai-config/models', name: 'AIModels', component: () => import('../views/AIModelsView.vue'), meta: { title: '模型目录' } },
      { path: '/ai-config/small-tasks', name: 'AISmallTasks', component: () => import('../views/AISmallTasksView.vue'), meta: { title: 'AI小任务' } },
      { path: '/ai-config/providers', name: 'AIProviders', component: () => import('../views/AIProvidersView.vue'), meta: { title: 'Provider配置' } },
      { path: '/ai-config/trials', name: 'AITrials', component: () => import('../views/AITrialsView.vue'), meta: { title: '试用期' } },
      { path: '/rbac', name: 'RBAC', component: () => import('../views/RBACView.vue'), meta: { title: '权限管理' } },
      { path: '/audit', name: 'Audit', component: () => import('../views/AuditView.vue'), meta: { title: '审计日志' } },
    ],
  },
];
