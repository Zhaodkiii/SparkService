<template>
  <a-space style="margin-bottom: 12px">
    <a-select v-model:value="windowDays" style="width: 140px" @change="load">
      <a-select-option :value="1">最近 1 天</a-select-option>
      <a-select-option :value="7">最近 7 天</a-select-option>
      <a-select-option :value="14">最近 14 天</a-select-option>
      <a-select-option :value="30">最近 30 天</a-select-option>
    </a-select>
    <a-button @click="load">刷新</a-button>
  </a-space>

  <a-row :gutter="12">
    <a-col :span="6"><a-card title="逻辑消息">{{ overview?.summary.message_total ?? 0 }}</a-card></a-col>
    <a-col :span="6"><a-card title="渠道投递">{{ overview?.summary.delivery_total ?? 0 }}</a-card></a-col>
    <a-col :span="6"><a-card title="已送达">{{ overview?.summary.delivery_delivered ?? 0 }}</a-card></a-col>
    <a-col :span="6"><a-card title="失败">{{ overview?.summary.delivery_failed ?? 0 }}</a-card></a-col>
  </a-row>

  <a-row :gutter="12" style="margin-top: 12px">
    <a-col :span="8" v-for="(row, channel) in overview?.by_channel || {}" :key="channel">
      <a-card :title="channelLabel(channel)">
        <div class="overview-channel">
          <div>消息：{{ row.messages }}</div>
          <div>投递：{{ row.deliveries }}</div>
          <div>送达：{{ row.delivered }}</div>
          <div>失败：{{ row.failed }}</div>
        </div>
      </a-card>
    </a-col>
  </a-row>

  <a-card title="最近消息" style="margin-top: 12px">
    <a-table :data-source="overview?.recent_messages || []" :pagination="false" row-key="id" size="small">
      <a-table-column title="ID" data-index="id" :width="80" />
      <a-table-column title="渠道" data-index="channel" :width="100" />
      <a-table-column title="状态" data-index="status" :width="100" />
      <a-table-column title="标题" data-index="title" />
      <a-table-column title="收件人" data-index="recipient" :width="220" />
      <a-table-column title="时间" key="created_at" :width="180">
        <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchNotificationOverview, type NotificationOverview } from '../api/modules/notifications';
import { formatDateTime } from '../utils/datetime';

const overview = ref<NotificationOverview | null>(null);
const windowDays = ref(7);

function channelLabel(channel: string) {
  if (channel === 'apns') return 'APNs';
  if (channel === 'email') return '邮箱';
  if (channel === 'sms') return '短信';
  return channel;
}

async function load() {
  overview.value = await fetchNotificationOverview({ window_days: windowDays.value });
}

onMounted(load);
</script>

<style scoped>
.overview-channel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}
</style>
