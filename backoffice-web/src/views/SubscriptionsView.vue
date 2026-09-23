<template>
  <a-card title="RevenueCat 订阅状态" :bordered="false" style="margin-bottom: 16px">
    <a-space wrap>
      <a-input-number v-model:value="userId" :min="1" :precision="0" placeholder="用户 ID" style="width: 160px" />
      <a-button type="primary" :loading="userLoading" @click="loadUser">查询用户权益</a-button>
      <a-button :disabled="!userId" :loading="syncing" @click="syncUser">重新同步</a-button>
    </a-space>

    <template v-if="userDetail">
      <a-descriptions bordered size="small" :column="4" style="margin-top: 16px">
        <a-descriptions-item label="用户 ID">{{ userDetail.user_id }}</a-descriptions-item>
        <a-descriptions-item label="有效 Pro">
          <a-tag :color="userDetail.summary.is_pro ? 'green' : 'default'">
            {{ userDetail.summary.is_pro ? '是' : '否' }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="权益来源">{{ userDetail.summary.effective_source || '-' }}</a-descriptions-item>
        <a-descriptions-item label="最近同步">{{ formatDateTime(userDetail.summary.last_synced_at) }}</a-descriptions-item>
      </a-descriptions>

      <a-table
        :data-source="userDetail.snapshots"
        :pagination="false"
        row-key="entitlement_identifier"
        size="small"
        style="margin-top: 16px"
      >
        <a-table-column title="Entitlement" data-index="entitlement_identifier" />
        <a-table-column title="环境" data-index="environment" />
        <a-table-column title="状态" data-index="status" />
        <a-table-column title="产品" data-index="product_id">
          <template #default="{ text }">{{ text || '-' }}</template>
        </a-table-column>
        <a-table-column title="到期时间" key="expires_at">
          <template #default="{ record }">{{ formatDateTime(record.expires_at) }}</template>
        </a-table-column>
        <a-table-column title="自动续费" key="will_renew">
          <template #default="{ record }">{{ record.will_renew ? '是' : '否' }}</template>
        </a-table-column>
      </a-table>

      <a-alert
        v-if="userDetail.ownership_conflict_count"
        type="warning"
        show-icon
        style="margin-top: 16px"
        :message="`检测到 ${userDetail.ownership_conflict_count} 次订阅归属冲突；系统不会自动转移订阅所有权。`"
      />
      <a-descriptions v-if="userDetail.ownerships?.length" title="订阅归属" bordered size="small" :column="3" style="margin-top: 16px">
        <a-descriptions-item v-for="ownership in userDetail.ownerships" :key="`${ownership.store}-${ownership.environment}-${ownership.first_bound_at}`" :label="`${ownership.store} / ${ownership.environment}`">
          {{ ownership.state === 'active' ? '原账户有效归属' : '注销墓碑' }} · {{ ownership.first_product_id || '-' }}
        </a-descriptions-item>
      </a-descriptions>
    </template>
  </a-card>

  <a-card title="Webhook Inbox" :bordered="false">
    <a-space wrap style="margin-bottom: 16px">
      <a-input-number v-model:value="filters.userId" :min="1" :precision="0" placeholder="匹配用户 ID" style="width: 150px" />
      <a-select v-model:value="filters.status" style="width: 140px">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option value="received">已接收</a-select-option>
        <a-select-option value="processing">处理中</a-select-option>
        <a-select-option value="processed">已处理</a-select-option>
        <a-select-option value="unmatched">待匹配</a-select-option>
        <a-select-option value="retryable">待重试</a-select-option>
        <a-select-option value="ownership_conflict">归属冲突</a-select-option>
        <a-select-option value="failed">失败</a-select-option>
      </a-select>
      <a-select v-model:value="filters.environment" style="width: 120px">
        <a-select-option value="">全部环境</a-select-option>
        <a-select-option value="production">生产</a-select-option>
        <a-select-option value="sandbox">沙盒</a-select-option>
      </a-select>
      <a-button type="primary" :loading="eventsLoading" @click="loadEvents(1)">查询</a-button>
    </a-space>

    <a-table :data-source="events.items" :loading="eventsLoading" :pagination="false" row-key="event_id" size="small" :scroll="{ x: 1120 }">
      <a-table-column title="事件" data-index="event_type" :width="150" />
      <a-table-column title="环境" data-index="environment" :width="100" />
      <a-table-column title="状态" key="process_status" :width="110">
        <template #default="{ record }">
          <a-tag :color="statusColor(record.process_status)">{{ record.process_status }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="用户 ID" data-index="matched_user_id" :width="100">
        <template #default="{ text }">{{ text ?? '-' }}</template>
      </a-table-column>
      <a-table-column title="尝试" data-index="attempt_count" :width="70" />
      <a-table-column title="错误" data-index="error_code" :width="160">
        <template #default="{ text }">{{ text || '-' }}</template>
      </a-table-column>
      <a-table-column title="接收时间" key="received_at" :width="180">
        <template #default="{ record }">{{ formatDateTime(record.received_at) }}</template>
      </a-table-column>
      <a-table-column title="事件 ID" data-index="event_id" :width="220" ellipsis />
      <a-table-column title="操作" key="actions" fixed="right" :width="100">
        <template #default="{ record }">
          <a-button v-if="record.process_status !== 'processed'" size="small" :loading="replayingEventId === record.event_id" @click="replay(record.event_id)">
            重放
          </a-button>
          <span v-else>-</span>
        </template>
      </a-table-column>
    </a-table>

    <a-pagination
      style="margin-top: 16px; text-align: right"
      :current="events.page"
      :page-size="events.page_size"
      :total="events.total"
      @change="loadEvents"
    />
  </a-card>
</template>

<script setup lang="ts">
import { message } from 'ant-design-vue';
import { reactive, ref } from 'vue';
import {
  fetchSubscriptionEvents,
  fetchSubscriptionUser,
  replaySubscriptionEvent,
  synchronizeSubscriptionUser,
  type SubscriptionEventListResponse,
  type SubscriptionUserDetail,
} from '../api/modules/subscriptions';

const userId = ref<number | null>(null);
const userLoading = ref(false);
const syncing = ref(false);
const userDetail = ref<SubscriptionUserDetail | null>(null);
const eventsLoading = ref(false);
const replayingEventId = ref('');
const filters = reactive({ userId: null as number | null, status: '', environment: '' });
const events = reactive<SubscriptionEventListResponse>({ items: [], page: 1, page_size: 20, total: 0 });

function formatDateTime(value?: string | null) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusColor(status: string) {
  if (status === 'processed') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'unmatched' || status === 'retryable') return 'orange';
  return 'blue';
}

async function loadUser() {
  if (!userId.value) return;
  userLoading.value = true;
  try {
    userDetail.value = await fetchSubscriptionUser(userId.value);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '查询订阅状态失败');
  } finally {
    userLoading.value = false;
  }
}

async function syncUser() {
  if (!userId.value) return;
  syncing.value = true;
  try {
    await synchronizeSubscriptionUser(userId.value);
    message.success('已完成同步');
    await loadUser();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '同步失败');
  } finally {
    syncing.value = false;
  }
}

async function loadEvents(page = events.page) {
  eventsLoading.value = true;
  try {
    const result = await fetchSubscriptionEvents({
      page,
      page_size: events.page_size,
      user_id: filters.userId ?? undefined,
      process_status: filters.status || undefined,
      environment: filters.environment || undefined,
    });
    Object.assign(events, result);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '查询 Webhook 事件失败');
  } finally {
    eventsLoading.value = false;
  }
}

async function replay(eventId: string) {
  replayingEventId.value = eventId;
  try {
    await replaySubscriptionEvent(eventId);
    message.success('已加入重放队列');
    await loadEvents();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '重放失败');
  } finally {
    replayingEventId.value = '';
  }
}

void loadEvents(1);
</script>
