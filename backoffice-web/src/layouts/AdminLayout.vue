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
          <a-sub-menu v-if="item.children?.length" :key="item.key" :title="item.label">
            <a-menu-item v-for="child in item.children" :key="child.key">{{ child.label }}</a-menu-item>
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
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';

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

const fallbackMenus = [
  { code: 'menu:dashboard', name: '仪表盘', path: '/dashboard', children: [] },
  { code: 'menu:tasks', name: '异步任务看板', path: '/tasks', children: [] },
  { code: 'menu:users', name: '用户管理', path: '/users', children: [] },
  {
    code: 'menu:ai',
    name: 'AI 场景配置',
    path: '/ai-config',
    children: [
      { code: 'menu:ai:scenario', name: 'AI 场景配置', path: '/ai-config/scenarios', children: [] },
      { code: 'menu:ai:models', name: '模型目录', path: '/ai-config/models', children: [] },
      { code: 'menu:ai:provider', name: 'Provider 配置', path: '/ai-config/providers', children: [] },
      { code: 'menu:ai:trial', name: '试用期', path: '/ai-config/trials', children: [] },
    ],
  },
  { code: 'menu:rbac', name: '权限管理', path: '/rbac', children: [] },
  { code: 'menu:audit', name: '审计日志', path: '/audit', children: [] },
];

const menus = computed(() => (auth.menus.length ? auth.menus : fallbackMenus));

const menuItems = computed(() =>
  menus.value.map((item) => ({
    key: item.path,
    label: item.name,
    children: (item.children || []).map((child) => ({ key: child.path, label: child.name })),
  })),
);

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
    if (path.startsWith('/ai-config/')) {
      openKeys.value = ['/ai-config'];
    }
  },
  { immediate: true },
);

function onMenuClick(info: { key: string }) {
  if (info.key === '/ai-config') {
    router.push('/ai-config/scenarios');
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
