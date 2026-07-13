<template>
  <div class="page">
    <a-card title="渠道设置">
      <template #extra><a-button @click="load">刷新</a-button></template>
      <a-alert
        message="此页展示运行时配置健康度，不展示密钥明文。实际密钥请通过环境变量或密钥管理系统维护。"
        type="info"
        show-icon
        class="notice"
      />
      <a-row :gutter="[16, 16]">
        <a-col v-for="item in channels" :key="item.channel" :span="8">
          <a-card :title="item.name" size="small" :loading="loading">
            <template #extra>
              <a-tag :color="item.enabled ? 'green' : 'red'">{{ item.enabled ? '可用' : '未就绪' }}</a-tag>
            </template>
            <a-descriptions :column="1" size="small" bordered>
              <a-descriptions-item label="渠道">{{ channelLabel(item.channel) }}</a-descriptions-item>
              <a-descriptions-item label="环境">{{ item.environment || '-' }}</a-descriptions-item>
              <a-descriptions-item v-for="(value, key) in item.config" :key="key" :label="configLabel(String(key))">
                <a-tag v-if="typeof value === 'boolean'" :color="value ? 'green' : 'red'">{{ value ? '已配置' : '未配置' }}</a-tag>
                <span v-else>{{ value || '-' }}</span>
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-col>
      </a-row>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { fetchNotificationChannelSettings, type NotificationChannelSetting } from '../api/modules/notifications';

const loading = ref(false);
const channels = ref<NotificationChannelSetting[]>([]);

function channelLabel(value: string) {
  return ({ apns: 'APNs', sms: '短信', email: '邮箱' } as Record<string, string>)[value] || value;
}

function configLabel(value: string) {
  return ({
    topic: 'Bundle Topic',
    key_id_configured: 'Key ID',
    team_id_configured: 'Team ID',
    auth_key_path_configured: 'Auth Key Path',
    endpoint: '服务地址',
    sign_name: '短信签名',
    access_key_configured: 'AccessKey',
    notification_template_configured: '通知模板',
    otp_template_configured: '验证码模板',
    host: 'SMTP Host',
    port: 'SMTP Port',
    default_from_email: '发件人',
    host_user_configured: 'SMTP 用户',
    host_password_configured: 'SMTP 密码',
    use_ssl: 'SSL',
    use_tls: 'TLS',
    timeout: '超时秒数',
  } as Record<string, string>)[value] || value;
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchNotificationChannelSettings();
    channels.value = data.channels;
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
.notice {
  margin-bottom: 16px;
}
</style>
