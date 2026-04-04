<template>
  <a-row :gutter="16">
    <a-col :span="8"><a-card title="用户总量">{{ overview?.users.total ?? '-' }}</a-card></a-col>
    <a-col :span="8"><a-card title="活跃用户">{{ overview?.users.active ?? '-' }}</a-card></a-col>
    <a-col :span="8"><a-card title="Staff 用户">{{ overview?.users.staff ?? '-' }}</a-card></a-col>
  </a-row>
  <a-row :gutter="16" style="margin-top: 16px">
    <a-col :span="8"><a-card title="聊天线程">{{ overview?.chat.threads ?? '-' }}</a-card></a-col>
    <a-col :span="8"><a-card title="聊天消息">{{ overview?.chat.messages ?? '-' }}</a-card></a-col>
    <a-col :span="8"><a-card title="医疗病例">{{ overview?.medical.cases ?? '-' }}</a-card></a-col>
  </a-row>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchDashboardOverview, type DashboardOverview } from '../api/modules/dashboard';

const overview = ref<DashboardOverview | null>(null);

onMounted(async () => {
  overview.value = await fetchDashboardOverview();
});
</script>
