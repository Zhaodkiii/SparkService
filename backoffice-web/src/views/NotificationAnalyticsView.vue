<template>
  <div class="page">
    <a-card title="统计分析">
      <template #extra>
        <a-select v-model:value="windowDays" style="width: 120px" @change="load">
          <a-select-option :value="1">近 1 天</a-select-option>
          <a-select-option :value="7">近 7 天</a-select-option>
          <a-select-option :value="30">近 30 天</a-select-option>
          <a-select-option :value="90">近 90 天</a-select-option>
        </a-select>
      </template>
      <a-row :gutter="16">
        <a-col :span="6"><a-card size="small" title="逻辑消息">{{ analytics?.summary.messages ?? 0 }}</a-card></a-col>
        <a-col :span="6"><a-card size="small" title="渠道投递">{{ analytics?.summary.deliveries ?? 0 }}</a-card></a-col>
        <a-col :span="6"><a-card size="small" title="供应商事件">{{ analytics?.summary.provider_events ?? 0 }}</a-card></a-col>
        <a-col :span="6"><a-card size="small" title="新增抑制">{{ analytics?.summary.suppressions ?? 0 }}</a-card></a-col>
      </a-row>
    </a-card>

    <a-card title="渠道表现">
      <a-table :data-source="analytics?.channel_stats || []" :pagination="false" row-key="channel" size="small" :loading="loading">
        <a-table-column title="渠道" data-index="channel">
          <template #default="{ text }">{{ channelLabel(text) }}</template>
        </a-table-column>
        <a-table-column title="消息数" data-index="message_total" />
        <a-table-column title="投递数" data-index="delivery_total" />
        <a-table-column title="已送达" data-index="delivered" />
        <a-table-column title="失败" data-index="failed" />
        <a-table-column title="送达率" data-index="success_rate">
          <template #default="{ text }">{{ text }}%</template>
        </a-table-column>
        <a-table-column title="失败率" data-index="failure_rate">
          <template #default="{ text }">{{ text }}%</template>
        </a-table-column>
      </a-table>
    </a-card>

    <a-row :gutter="16">
      <a-col :span="12">
        <a-card title="消息状态分布">
          <a-table :data-source="analytics?.message_status_stats || []" :pagination="false" row-key="status" size="small">
            <a-table-column title="状态" data-index="status" />
            <a-table-column title="数量" data-index="count" />
          </a-table>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card title="投递状态分布">
          <a-table :data-source="analytics?.delivery_status_stats || []" :pagination="false" row-key="status" size="small">
            <a-table-column title="状态" data-index="status" />
            <a-table-column title="数量" data-index="count" />
          </a-table>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchNotificationAnalytics, type NotificationAnalytics } from '../api/modules/notifications';

const loading = ref(false);
const windowDays = ref(7);
const analytics = ref<NotificationAnalytics | null>(null);

function channelLabel(value: string) {
  return ({ apns: 'APNs', sms: '短信', email: '邮箱' } as Record<string, string>)[value] || value;
}

async function load() {
  loading.value = true;
  try {
    analytics.value = await fetchNotificationAnalytics({ window_days: windowDays.value });
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.page {
  display: grid;
  gap: 16px;
}
</style>
