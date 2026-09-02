<template>
  <a-layout class="hospital-system-layout">
    <a-layout-header class="hospital-system-header">
      <div class="hospital-identity">
        <div class="hospital-logo" aria-hidden="true">医</div>
        <div class="hospital-identity-copy">
          <div class="hospital-title-row">
            <span class="hospital-name">{{ hospital?.name || '医院系统' }}</span>
            <span v-if="hospital" class="hospital-code">{{ hospital.code }}</span>
            <a-tag v-if="hospital" :color="HOSPITAL_STATUS_COLOR[hospital.status]">
              {{ HOSPITAL_STATUS_LABEL[hospital.status] }}
            </a-tag>
          </div>
          <div v-if="hospital" class="hospital-subtitle">
            {{ regionText(hospital) }} · {{ SERVICE_MODE_LABEL[hospital.service_mode] }}
          </div>
        </div>
      </div>
      <div class="hospital-session">
        <span class="session-user">{{ auth.user?.username || '当前管理员' }}</span>
        <a-button type="link" @click="logout">退出登录</a-button>
      </div>
    </a-layout-header>

    <a-layout-content class="hospital-system-content">
      <a-alert v-if="errorText" type="error" show-icon :message="errorText" />
      <template v-else>
        <nav class="hospital-nav" aria-label="医院系统导航">
          <router-link
            v-for="item in navItems"
            :key="item.key"
            :to="{ name: 'HospitalSystemSection', params: { hospitalId, tab: item.key } }"
            class="hospital-nav-item"
            :class="{ active: currentTab === item.key }"
          >
            {{ item.label }}
          </router-link>
        </nav>
        <div class="hospital-page-content">
          <router-view />
        </div>
      </template>
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { fetchHospital, hospitalCareMessage, type HospitalRow } from '../api/modules/hospitalCare';
import { HOSPITAL_STATUS_COLOR, HOSPITAL_STATUS_LABEL, SERVICE_MODE_LABEL } from '../views/hospital-care/hospitalCareLabels';

const navItems = [
  { key: 'overview', label: '概览' },
  { key: 'base', label: '基础资料' },
  { key: 'departments', label: '科室' },
  { key: 'people', label: '职工与医生' },
  { key: 'agents', label: '智能体' },
  { key: 'knowledge', label: '知识库' },
  { key: 'integration', label: '服务接入' },
  { key: 'audit', label: '审计记录' },
];

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const hospital = ref<HospitalRow | null>(null);
const errorText = ref('');
const hospitalId = computed(() => String(route.params.hospitalId || ''));
const currentTab = computed(() => String(route.params.tab || 'overview'));

function regionText(row: HospitalRow) {
  return [row.province_code, row.city_code, row.district_code].filter(Boolean).join(' / ') || '--';
}

async function loadHospital() {
  try {
    hospital.value = await fetchHospital(hospitalId.value);
  } catch (error) {
    errorText.value = hospitalCareMessage(error);
  }
}

function logout() {
  auth.logout();
  router.replace('/login');
}

onMounted(loadHospital);
</script>

<style scoped>
.hospital-system-layout {
  min-height: 100vh;
  background: #f5f7fa;
}

.hospital-system-header {
  height: 84px;
  box-sizing: border-box;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #edf0f4;
  line-height: normal;
}

.hospital-identity,
.hospital-title-row,
.hospital-session {
  display: flex;
  align-items: center;
}

.hospital-identity {
  gap: 14px;
}

.hospital-logo {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #1677ff;
  background: #eaf3ff;
  font-weight: 700;
  font-size: 20px;
}

.hospital-identity-copy {
  min-width: 0;
}

.hospital-title-row {
  gap: 10px;
}

.hospital-name {
  color: #182230;
  font-size: 20px;
  font-weight: 650;
}

.hospital-code,
.hospital-subtitle,
.session-user {
  color: #8a94a6;
  font-size: 13px;
}

.hospital-subtitle {
  margin-top: 4px;
}

.hospital-session {
  gap: 14px;
}

.hospital-system-content {
  width: 100%;
  padding: 0;
  box-sizing: border-box;
}

.hospital-nav {
  display: flex;
  gap: 34px;
  min-height: 58px;
  align-items: stretch;
  padding: 0 32px;
  box-sizing: border-box;
  background: #fff;
  border-bottom: 1px solid #e8ebf0;
}

.hospital-nav-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  color: #3c4655;
  text-decoration: none;
  font-size: 15px;
  font-weight: 500;
}

.hospital-nav-item:hover,
.hospital-nav-item.active {
  color: #1677ff;
}

.hospital-nav-item.active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: #1677ff;
  content: '';
}

.hospital-page-content {
  width: 100%;
  min-height: calc(100vh - 142px);
  margin: 0;
  padding: 28px 40px 56px;
  background: #f5f7fa;
  box-sizing: border-box;
}

@media (max-width: 800px) {
  .hospital-system-header {
    height: auto;
    min-height: 84px;
    padding: 16px;
    gap: 12px;
  }

  .hospital-session .session-user {
    display: none;
  }

  .hospital-system-content {
    overflow-x: auto;
  }

  .hospital-nav {
    gap: 22px;
    min-width: 680px;
    padding: 0 16px;
  }

  .hospital-page-content {
    min-width: 980px;
    padding: 20px 16px 40px;
  }
}
</style>
