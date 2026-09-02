<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px">
      <div>
        <a-typography-title :level="4" style="margin: 0">医院管理 / 医院列表</a-typography-title>
        <a-typography-text type="secondary">管理接入平台的医院、服务状态和基础配置</a-typography-text>
      </div>
      <a-button v-if="canCreate" type="primary" @click="router.push('/hospital-care/hospitals/new')">新增医院</a-button>
    </div>

    <a-space wrap style="margin-bottom: 16px">
      <a-statistic title="医院总数" :value="counts.total" />
      <a-statistic title="已启用" :value="counts.active" />
      <a-statistic title="草稿" :value="counts.draft" />
      <a-statistic title="已暂停" :value="counts.suspended" />
    </a-space>

    <a-space wrap style="margin-bottom: 16px">
      <a-input-search v-model:value="query.q" placeholder="搜索医院名称/编码" enter-button style="width: 280px" @search="onSearch" />
      <a-select v-model:value="query.status" style="width: 140px" @change="onSearch">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option value="draft">草稿</a-select-option>
        <a-select-option value="active">已启用</a-select-option>
        <a-select-option value="suspended">已暂停</a-select-option>
      </a-select>
      <a-select v-model:value="query.service_mode" style="width: 180px" @change="onSearch">
        <a-select-option value="">全部服务模式</a-select-option>
        <a-select-option value="demo">Demo 演示</a-select-option>
        <a-select-option value="redirect">跳转官方入口</a-select-option>
        <a-select-option value="integrated">HIS 已接入</a-select-option>
      </a-select>
      <a-button type="primary" @click="onSearch">查询</a-button>
      <a-button @click="onReset">重置</a-button>
    </a-space>

    <a-alert v-if="errorText" type="error" show-icon :message="errorText" style="margin-bottom: 16px">
      <template #action>
        <a-button size="small" @click="load">重试</a-button>
      </template>
    </a-alert>

    <a-table :data-source="rows" row-key="id" :pagination="false" :loading="loading" :scroll="{ x: 1280 }">
      <template #emptyText>
        <a-empty :description="emptyText">
          <a-button v-if="canCreate && !hasFilter" type="primary" @click="router.push('/hospital-care/hospitals/new')">新增医院</a-button>
          <a-button v-else-if="hasFilter" @click="onReset">清除筛选</a-button>
        </a-empty>
      </template>
      <a-table-column title="医院名称" key="name" :width="220">
        <template #default="{ record }">
          <a-button type="link" style="padding: 0" @click="openDetail(record.id)">{{ record.name }}</a-button>
        </template>
      </a-table-column>
      <a-table-column title="编码" data-index="code" :width="140" />
      <a-table-column title="地区" key="region" :width="160">
        <template #default="{ record }">{{ regionText(record) }}</template>
      </a-table-column>
      <a-table-column title="等级" key="grade" :width="90">
        <template #default="{ record }">{{ record.grade || '--' }}</template>
      </a-table-column>
      <a-table-column title="服务模式" key="service_mode" :width="140">
        <template #default="{ record }">{{ serviceModeLabel(record.service_mode) }}</template>
      </a-table-column>
      <a-table-column title="科室 / 医生" key="counts" :width="120">
        <template #default="{ record }">{{ record.department_count ?? 0 }} / {{ record.doctor_count ?? 0 }}</template>
      </a-table-column>
      <a-table-column title="状态" key="status" :width="100">
        <template #default="{ record }">
          <a-tag :color="hospitalStatusColor(record.status)">{{ hospitalStatusLabel(record.status) }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" @click="openDetail(record.id)">详情</a-button>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { fetchHospitals, hospitalCareMessage, type HospitalCounts, type HospitalRow } from '../../api/modules/hospitalCare';
import type { Pagination } from '../../types';
import { useAuthStore } from '../../stores/auth';
import TableHoverActions from '../../components/TableHoverActions.vue';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';
import { HOSPITAL_STATUS_COLOR, HOSPITAL_STATUS_LABEL, SERVICE_MODE_LABEL } from './hospitalCareLabels';

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const errorText = ref('');
const rows = ref<HospitalRow[]>([]);
const counts = reactive<HospitalCounts>({ total: 0, active: 0, draft: 0, suspended: 0 });
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const query = reactive({ page: 1, page_size: 20, q: '', status: '', service_mode: '' });

const canCreate = computed(() => auth.hasPermission('button:hospital_care:hospital:create'));
const hasFilter = computed(() => Boolean(query.q || query.status || query.service_mode));
const emptyText = computed(() => (hasFilter.value ? '当前筛选无结果' : '尚未新增医院'));
const actionsColWidth = computed(() => calcActionsColWidth({ buttons: 1, min: 80, perButton: 64 }));

function regionText(row: HospitalRow) {
  return [row.province_code, row.city_code, row.district_code].filter(Boolean).join(' / ') || '--';
}

function serviceModeLabel(value: string) {
  return SERVICE_MODE_LABEL[value as keyof typeof SERVICE_MODE_LABEL] || value;
}

function hospitalStatusLabel(value: string) {
  return HOSPITAL_STATUS_LABEL[value as keyof typeof HOSPITAL_STATUS_LABEL] || value;
}

function hospitalStatusColor(value: string) {
  return HOSPITAL_STATUS_COLOR[value as keyof typeof HOSPITAL_STATUS_COLOR] || 'default';
}

function openDetail(id: string) {
  const target = router.resolve({ name: 'HospitalSystemSection', params: { hospitalId: id, tab: 'overview' } });
  const features = [
    'popup=yes',
    `width=${Math.max(window.screen.availWidth, 1280)}`,
    `height=${Math.max(window.screen.availHeight, 800)}`,
    'left=0',
    'top=0',
  ].join(',');
  const hospitalWindow = window.open(target.href, 'spark-hospital-system', features);
  hospitalWindow?.focus();
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchHospitals(query);
    rows.value = data.items;
    Object.assign(pagination, data.pagination);
    Object.assign(counts, data.counts);
    errorText.value = '';
  } catch (error) {
    errorText.value = hospitalCareMessage(error);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  query.page = 1;
  load();
}

function onReset() {
  query.q = '';
  query.status = '';
  query.service_mode = '';
  query.page = 1;
  load();
}

function onPageChange(page: number, pageSize: number) {
  query.page = page;
  query.page_size = pageSize;
  load();
}

onMounted(load);
</script>
