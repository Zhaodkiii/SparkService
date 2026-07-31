<template>
  <a-layout class="layout-root">
    <a-layout-sider :collapsed="collapsed" collapsible @collapse="(v: boolean) => (collapsed = v)">
      <div class="logo">Spark Admin</div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="[activeKey]"
        :open-keys="openKeys"
        @openChange="onOpenChange"
        @click="onMenuClick"
      >
        <template v-for="item in menuItems" :key="item.key">
          <a-sub-menu v-if="item.children?.length" :key="item.key">
            <template #title>{{ item.label }}</template>
            <template v-for="child in item.children" :key="child.key">
              <a-sub-menu v-if="child.children?.length" :key="child.key">
                <template #title>{{ child.label }}</template>
                <a-menu-item v-for="grand in child.children" :key="grand.key">{{ grand.label }}</a-menu-item>
              </a-sub-menu>
              <a-menu-item v-else :key="child.key">{{ child.label }}</a-menu-item>
            </template>
          </a-sub-menu>
          <a-menu-item v-else :key="item.key">{{ item.label }}</a-menu-item>
        </template>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="header-bar">
        <div>{{ auth.user?.username }}</div>
        <a-button type="link" @click="logout">退出登录</a-button>
      </a-layout-header>
      <div class="tabs-wrap">
        <a-tabs
          hide-add
          type="editable-card"
          :active-key="activeKey"
          @change="onTabChange"
          @edit="onTabEdit"
        >
          <a-tab-pane
            v-for="tab in tabs"
            :key="tab.key"
            :tab="tab.title"
            :closable="tab.closable"
          />
        </a-tabs>
      </div>
      <a-layout-content class="content-area">
        <router-view v-slot="{ Component, route: currentRoute }">
          <keep-alive :max="20">
            <component
              :is="Component"
              v-if="Component"
              :key="tabCacheKey(currentRoute.fullPath)"
            />
          </keep-alive>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, provide, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { updateTabTitleKey } from '../composables/useAdminTabs';

interface TabItem {
  key: string;
  title: string;
  closable: boolean;
}

const collapsed = ref(false);
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const activeKey = computed(() => route.path);
const openKeys = ref<string[]>([]);
const tabs = reactive<TabItem[]>([{ key: '/dashboard', title: '仪表盘', closable: false }]);
const routeCacheVersion = reactive<Record<string, number>>({});
const notificationRecordPaths = new Set([
  '/notifications/records/all',
  '/notifications/apns',
  '/notifications/sms',
  '/notifications/email',
]);

function tabCacheKey(path: string) {
  return `${path}::${routeCacheVersion[path] ?? 0}`;
}

function updateTabTitle(path: string, title: string) {
  const tab = tabs.find((item) => item.key === path);
  if (tab) {
    tab.title = title;
  }
}

provide(updateTabTitleKey, updateTabTitle);

const fallbackMenus = [
  { code: 'menu:dashboard', name: '仪表盘', path: '/dashboard', children: [] },
  {
    code: 'menu:tasks',
    name: '异步任务',
    path: '/tasks',
    children: [
      { code: 'menu:tasks:dashboard', name: '异步任务看板', path: '/tasks', children: [] },
      { code: 'menu:tasks:manager', name: '异步任务管理', path: '/tasks/manager', children: [] },
    ],
  },
  {
    code: 'menu:users',
    name: '用户管理',
    path: '/users',
    children: [
      { code: 'menu:users:list', name: '用户管理', path: '/users', children: [] },
      { code: 'menu:users:devices', name: '设备管理', path: '/users/devices', children: [] },
      { code: 'menu:users:deactivations', name: '注销管理', path: '/users/deactivations', children: [] },
    ],
  },
  {
    code: 'menu:notifications',
    name: '通知中心',
    path: '/notifications',
    children: [
      { code: 'menu:notifications:overview', name: '总览', path: '/notifications/overview', children: [] },
      { code: 'menu:notifications:users', name: '通知用户列表', path: '/notifications/users', children: [] },
      { code: 'menu:notifications:templates', name: '通知模板', path: '/notifications/templates', children: [] },
      { code: 'menu:notifications:campaigns', name: '发送活动', path: '/notifications/campaigns', children: [] },
      {
        code: 'menu:notifications:records',
        name: '发送记录',
        path: '/notifications/records',
        children: [
          { code: 'menu:notifications:records:all', name: '全渠道记录', path: '/notifications/records/all', children: [] },
          { code: 'menu:notifications:records:apns', name: 'APNs 发送记录', path: '/notifications/apns', children: [] },
          { code: 'menu:notifications:records:sms', name: '短信发送记录', path: '/notifications/sms', children: [] },
          { code: 'menu:notifications:records:email', name: '邮箱发送记录', path: '/notifications/email', children: [] },
        ],
      },
      { code: 'menu:notifications:suppressions', name: '异常与抑制', path: '/notifications/suppressions', children: [] },
      { code: 'menu:notifications:analytics', name: '统计分析', path: '/notifications/analytics', children: [] },
      { code: 'menu:notifications:channel_settings', name: '渠道设置', path: '/notifications/channel-settings', children: [] },
    ],
  },
  {
    code: 'menu:version',
    name: '版本控制',
    path: '/version',
    children: [
      { code: 'menu:version:configs', name: '版本配置', path: '/version/configs', children: [] },
      { code: 'menu:version:logs', name: '检查日志', path: '/version/logs', children: [] },
    ],
  },
  {
    code: 'menu:ai',
    name: 'AI 场景配置',
    path: '/ai-config',
    children: [
      { code: 'menu:ai:scenario', name: 'AI 场景配置', path: '/ai-config/scenarios', children: [] },
      { code: 'menu:ai:models', name: '模型目录', path: '/ai-config/models', children: [] },
      { code: 'menu:ai:small_tasks', name: 'AI 小任务', path: '/ai-config/small-tasks', children: [] },
      { code: 'menu:ai:provider', name: 'Provider 配置', path: '/ai-config/providers', children: [] },
      { code: 'menu:ai:trial', name: '试用期', path: '/ai-config/trials', children: [] },
    ],
  },
  { code: 'menu:rbac', name: '权限管理', path: '/rbac', children: [] },
  {
    code: 'menu:audit',
    name: '审计日志',
    path: '/audit',
    children: [
      { code: 'menu:audit:operator', name: '操作员日志', path: '/audit/admin', children: [] },
      { code: 'menu:audit:system', name: '系统日志', path: '/audit/system', children: [] },
    ],
  },
  {
    code: 'menu:conversations',
    name: '对话',
    path: '/conversations',
    children: [{ code: 'menu:conversations:users', name: '用户对话', path: '/conversations/users', children: [] }],
  },
  {
    code: 'menu:medical_data',
    name: '医疗数据',
    path: '/medical-data',
    children: [
      { code: 'menu:medical_data:users', name: '用户医疗数据', path: '/medical-data/users', children: [] },
      { code: 'menu:medical_data:quality', name: '数据质检', path: '/medical-data/quality', children: [] },
      { code: 'menu:medical_data:attachments', name: '附件与识别', path: '/medical-data/attachments', children: [] },
      { code: 'menu:medical_data:analytics', name: '医疗数据统计', path: '/medical-data/analytics', children: [] },
    ],
  },
  {
    code: 'menu:articles',
    name: '文章模块',
    path: '/articles',
    children: [
      { code: 'menu:articles:overview', name: '文章总览', path: '/articles/overview', children: [] },
      { code: 'menu:articles:list', name: '文章管理', path: '/articles/list', children: [] },
      { code: 'menu:articles:categories', name: '分类管理', path: '/articles/categories', children: [] },
      { code: 'menu:articles:tags', name: '标签管理', path: '/articles/tags', children: [] },
      { code: 'menu:articles:locales', name: '多语言管理', path: '/articles/locales', children: [] },
      { code: 'menu:articles:analytics', name: '阅读数据', path: '/articles/analytics', children: [] },
      { code: 'menu:articles:compliance', name: '来源合规', path: '/articles/compliance', children: [] },
      { code: 'menu:articles:recycle_bin', name: '回收站', path: '/articles/recycle-bin', children: [] },
    ],
  },
];

const menus = computed(() => {
  const source = auth.menus.length ? auth.menus : fallbackMenus;
  if (auth.user?.is_superuser) {
    return source;
  }
  return source.filter((item) => item.code !== 'menu:conversations');
});

const menuItems = computed(() =>
  menus.value.map((item) => ({
    key: item.path,
    label: item.name,
    children: (item.children || []).map((child) => ({
      key: child.path,
      label: child.name,
      children: (child.children || []).map((grand) => ({ key: grand.path, label: grand.name })),
    })),
  })),
);

function resolveOpenKeys(path: string) {
  if (path.startsWith('/ai-config/')) {
    return ['/ai-config'];
  }
  if (path.startsWith('/notifications/')) {
    return notificationRecordPaths.has(path) ? ['/notifications', '/notifications/records'] : ['/notifications'];
  }
  if (path.startsWith('/version/')) {
    return ['/version'];
  }
  if (path === '/tasks' || path.startsWith('/tasks/')) {
    return ['/tasks'];
  }
  if (path.startsWith('/users/')) {
    return ['/users'];
  }
  if (path.startsWith('/conversations/')) {
    return ['/conversations'];
  }
  if (path.startsWith('/medical-data/')) {
    return ['/medical-data'];
  }
  if (path.startsWith('/articles/')) {
    return ['/articles'];
  }
  if (path.startsWith('/audit/')) {
    return ['/audit'];
  }
  return [];
}

watch(
  () => route.path,
  (path) => {
    if (path === '/login' || path === '/') {
      return;
    }
    const exists = tabs.some((tab) => tab.key === path);
    if (!exists) {
      tabs.push({
        key: path,
        title: String(route.meta.title || path),
        closable: path !== '/dashboard',
      });
    }
    openKeys.value = resolveOpenKeys(path);
  },
  { immediate: true },
);

function onMenuClick(info: { key: string }) {
  if (info.key === '/ai-config') {
    router.push('/ai-config/scenarios');
    return;
  }
  if (info.key === '/version') {
    router.push('/version/configs');
    return;
  }
  if (info.key === '/conversations') {
    router.push('/conversations/users');
    return;
  }
  if (info.key === '/medical-data') {
    router.push('/medical-data/users');
    return;
  }
  if (info.key === '/articles') {
    router.push('/articles/overview');
    return;
  }
  router.push(info.key);
}

function onTabChange(key: string) {
  router.push(key);
}

function onTabEdit(targetKey: string | MouseEvent | KeyboardEvent, action: 'add' | 'remove') {
  if (action !== 'remove') {
    return;
  }
  const key = String(targetKey);
  const index = tabs.findIndex((tab) => tab.key === key);
  if (index < 0 || !tabs[index].closable) {
    return;
  }
  tabs.splice(index, 1);
  routeCacheVersion[key] = (routeCacheVersion[key] ?? 0) + 1;

  if (route.path === key) {
    const fallback = tabs[index - 1] || tabs[index] || tabs[0];
    router.push(fallback?.key || '/dashboard');
  }
}

function onOpenChange(keys: string[]) {
  openKeys.value = keys;
}

function logout() {
  auth.logout();
  router.replace('/login');
}
</script>

<style scoped>
.layout-root {
  min-height: 100vh;
}
.logo {
  height: 48px;
  margin: 8px;
  color: #fff;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.header-bar {
  background: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
}
.tabs-wrap {
  background: #fff;
  padding: 8px 16px 0;
}
.content-area {
  margin: 16px;
  background: #fff;
  padding: 16px;
}
</style>
