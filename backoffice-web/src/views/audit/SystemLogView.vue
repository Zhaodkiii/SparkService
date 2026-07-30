<template>
  <a-alert type="info" show-icon style="margin-bottom: 12px">
    <template #message>日志路径</template>
    <template #description>
      <div>当前日志根目录：{{ pathInfo.log_root || '-' }}</div>
      <div>当前查询日期：{{ query.date }}</div>
      <div>当前日志文件：{{ pathInfo.log_file || currentLogFileLabel }}</div>
      <div v-if="pathInfo.host_path_hint">
        生产宿主机路径通常为：{{ pathInfo.host_path_hint }}/{{ query.date }}/
      </div>
      <div v-if="pathInfo.host_log_file">宿主机日志文件：{{ pathInfo.host_log_file }}</div>
      <div v-if="pathInfo.file_exists === false">当前日期/模块对应日志文件不存在</div>
    </template>
  </a-alert>

  <a-space style="margin-bottom: 16px" wrap>
    <a-date-picker v-model:value="fileDate" @change="onFileDateChange" />
    <a-select v-model:value="query.module" style="width: 180px" @change="loadLogs">
      <a-select-option v-for="item in modules" :key="item.value" :value="item.value">
        {{ item.label }}
      </a-select-option>
    </a-select>
    <a-select v-model:value="query.status" style="width: 120px" allow-clear placeholder="状态" @change="loadLogs">
      <a-select-option value="">全部</a-select-option>
      <a-select-option value="2xx">2xx</a-select-option>
      <a-select-option value="3xx">3xx</a-select-option>
      <a-select-option value="4xx">4xx</a-select-option>
      <a-select-option value="5xx">5xx</a-select-option>
      <a-select-option value="200">200</a-select-option>
      <a-select-option value="401">401</a-select-option>
      <a-select-option value="403">403</a-select-option>
      <a-select-option value="500">500</a-select-option>
      <a-select-option value="failed">failed</a-select-option>
    </a-select>
    <a-select v-model:value="query.level" style="width: 120px" allow-clear placeholder="级别" @change="loadLogs">
      <a-select-option value="DEBUG">DEBUG</a-select-option>
      <a-select-option value="INFO">INFO</a-select-option>
      <a-select-option value="WARNING">WARNING</a-select-option>
      <a-select-option value="ERROR">ERROR</a-select-option>
      <a-select-option value="CRITICAL">CRITICAL</a-select-option>
    </a-select>
    <a-input-search v-model:value="query.request_id" placeholder="request_id" enter-button @search="loadLogs" style="width: 240px" />
    <a-input v-model:value="query.path" placeholder="路径" allow-clear @pressEnter="loadLogs" style="width: 220px" />
    <a-input-search v-model:value="query.keyword" placeholder="关键字" enter-button @search="loadLogs" style="width: 200px" />
    <a-segmented v-model:value="query.order" :options="orderOptions" @change="loadLogs" />
  </a-space>

  <a-alert
    v-if="scanLimited"
    type="warning"
    show-icon
    message="日志文件较大，本次只扫描前 200000 行"
    style="margin-bottom: 12px"
  />

  <a-table
    :data-source="rows"
    :pagination="false"
    row-key="id"
    :loading="loading"
    :scroll="{ x: 1600 }"
  >
    <a-table-column title="时间" key="timestamp" :width="180">
      <template #default="{ record }">
        {{ formatDateTime(record.timestamp) }}
      </template>
    </a-table-column>
    <a-table-column title="级别" key="level" :width="96">
      <template #default="{ record }">
        <a-tag :color="levelColor(record.level)">{{ record.level || '-' }}</a-tag>
      </template>
    </a-table-column>
    <a-table-column title="logger" data-index="logger" :width="160" :ellipsis="true" />
    <a-table-column title="状态" key="status_code" :width="90">
      <template #default="{ record }">{{ record.status_code ?? '-' }}</template>
    </a-table-column>
    <a-table-column title="耗时" key="duration_ms" :width="90">
      <template #default="{ record }">
        {{ record.duration_ms === undefined || record.duration_ms === null ? '-' : `${record.duration_ms}ms` }}
      </template>
    </a-table-column>
    <a-table-column title="request_id" data-index="request_id" :width="260" :ellipsis="true" />
    <a-table-column title="路径" data-index="path" :width="260" :ellipsis="true" />
    <a-table-column title="消息" data-index="message" :ellipsis="true" />
    <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
      <template #default="{ record }">
        <TableHoverActions>
          <a-button size="small" @click="openDetail(record)">详情</a-button>
          <a-button v-if="record.request_id" size="small" @click="filterByRequestId(record.request_id)">
            同 request_id
          </a-button>
          <a-button v-if="record.request_id" size="small" @click="copyText(record.request_id)">复制</a-button>
        </TableHoverActions>
      </template>
    </a-table-column>
  </a-table>

  <a-pagination
    style="margin-top: 16px; text-align: right"
    :current="query.page"
    :page-size="query.page_size"
    :total="pagination.total"
    @change="onPageChange"
  />

  <SystemLogDetailDrawer
    :open="detailOpen"
    :loading="detailLoading"
    :detail="detail"
    @close="detailOpen = false"
    @jump-request="filterByRequestId"
  />
</template>

<script setup lang="ts">
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import { message } from 'ant-design-vue';
import { computed, onMounted, reactive, ref } from 'vue';
import TableHoverActions from '../../components/TableHoverActions.vue';
import {
  fetchSystemLogDetail,
  fetchSystemLogModules,
  fetchSystemLogs,
  type SystemLogDetail,
  type SystemLogItem,
  type SystemLogModule,
  type SystemLogQueryContext,
} from '../../api/modules/audit';
import type { Pagination } from '../../types';
import { formatDateTime } from '../../utils/datetime';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';
import SystemLogDetailDrawer from './SystemLogDetailDrawer.vue';

const actionsColWidth = computed(() =>
  calcActionsColWidth({
    buttons: 3,
    min: 220,
    perButton: 64,
  }),
);

const loading = ref(false);
const scanLimited = ref(false);
const rows = ref<SystemLogItem[]>([]);
const modules = ref<SystemLogModule[]>([]);
const pathInfo = reactive<SystemLogQueryContext>({
  log_root: '',
  date_pattern: 'YYYY-MM-DD',
  host_path_hint: '',
});
const currentLogFileLabel = computed(() => {
  const moduleItem = modules.value.find((item) => item.value === query.module);
  if (!pathInfo.log_root || !moduleItem) return '-';
  return `${pathInfo.log_root}/${query.date}/${moduleItem.file}`;
});
const fileDate = ref<Dayjs>(dayjs());
const pagination = reactive<Pagination>({ page: 1, page_size: 50, total: 0, total_pages: 0 });
const query = reactive({
  date: dayjs().format('YYYY-MM-DD'),
  module: 'access',
  level: '',
  status: '',
  request_id: '',
  path: '',
  keyword: '',
  page: 1,
  page_size: 50,
  order: 'desc' as 'asc' | 'desc',
});
const orderOptions = [
  { label: '新到旧', value: 'desc' },
  { label: '旧到新', value: 'asc' },
];

const detailOpen = ref(false);
const detailLoading = ref(false);
const detail = ref<SystemLogDetail | null>(null);

function levelColor(level: string) {
  if (level === 'ERROR' || level === 'CRITICAL') return 'red';
  if (level === 'WARNING') return 'orange';
  if (level === 'INFO') return 'blue';
  return 'default';
}

async function loadModules() {
  const data = await fetchSystemLogModules();
  modules.value = data.items;
  pathInfo.log_root = data.log_root;
  pathInfo.date_pattern = data.date_pattern;
  pathInfo.host_path_hint = data.host_path_hint;
  if (!modules.value.some((item) => item.value === query.module) && modules.value.length) {
    query.module = modules.value[0].value;
  }
}

function applyQueryContext(context?: SystemLogQueryContext) {
  if (!context) return;
  pathInfo.log_root = context.log_root || pathInfo.log_root;
  pathInfo.date_pattern = context.date_pattern || pathInfo.date_pattern;
  pathInfo.host_path_hint = context.host_path_hint ?? pathInfo.host_path_hint;
  pathInfo.date = context.date;
  pathInfo.file = context.file;
  pathInfo.log_file = context.log_file;
  pathInfo.host_log_file = context.host_log_file;
  pathInfo.file_exists = context.file_exists;
}

async function loadLogs() {
  loading.value = true;
  try {
    const data = await fetchSystemLogs(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
    scanLimited.value = Boolean(data.scan_limited);
    applyQueryContext(data.context);
  } finally {
    loading.value = false;
  }
}

function onFileDateChange(value: Dayjs | string | null) {
  query.date = value ? dayjs(value).format('YYYY-MM-DD') : dayjs().format('YYYY-MM-DD');
  loadLogs();
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  loadLogs();
}

async function openDetail(record: SystemLogItem) {
  detailOpen.value = true;
  detailLoading.value = true;
  detail.value = null;
  try {
    detail.value = await fetchSystemLogDetail({
      date: record.date,
      module: record.module,
      line_no: record.line_no,
    });
  } finally {
    detailLoading.value = false;
  }
}

function filterByRequestId(requestId: string) {
  query.request_id = requestId;
  query.page = 1;
  loadLogs();
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    message.success('已复制 request_id');
  } catch {
    message.error('复制失败');
  }
}

onMounted(async () => {
  await loadModules();
  await loadLogs();
});
</script>
