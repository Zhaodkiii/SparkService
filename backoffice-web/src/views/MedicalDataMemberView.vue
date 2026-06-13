<template>
  <div class="page-header">
    <a-breadcrumb>
      <a-breadcrumb-item><router-link to="/medical-data/users">医疗数据</router-link></a-breadcrumb-item>
      <a-breadcrumb-item><router-link :to="`/medical-data/users/${userId}`">用户 {{ userId }}</router-link></a-breadcrumb-item>
      <a-breadcrumb-item>成员 {{ memberId }}</a-breadcrumb-item>
    </a-breadcrumb>
  </div>

  <a-spin :spinning="loadingOverview">
    <a-descriptions v-if="overview?.member" bordered size="small" :column="4" style="margin-bottom: 16px">
      <a-descriptions-item label="成员">{{ overview.member.name }}</a-descriptions-item>
      <a-descriptions-item label="关系">{{ overview.member.relationship_label }}</a-descriptions-item>
      <a-descriptions-item label="性别">{{ displayGender(overview.member) }}</a-descriptions-item>
      <a-descriptions-item label="年龄">{{ overview.member.age ?? '-' }}</a-descriptions-item>
      <a-descriptions-item label="数据总数">{{ overview.member.total_count }}</a-descriptions-item>
      <a-descriptions-item label="附件">{{ overview.member.attachment_count }}</a-descriptions-item>
      <a-descriptions-item label="最近更新">{{ formatDateTime(overview.member.last_updated_at) }}</a-descriptions-item>
      <a-descriptions-item label="共享">{{ overview.member.share_summary }}</a-descriptions-item>
      <a-descriptions-item label="入口用户">#{{ userId }}</a-descriptions-item>
    </a-descriptions>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col v-for="card in statCards" :key="card.key" :span="3">
        <a-card size="small">
          <a-statistic :title="card.label" :value="card.value" />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="12">
        <a-card size="small" title="分类数量">
          <div v-for="bar in categoryBars" :key="bar.label" class="bar-row">
            <span class="bar-label">{{ bar.label }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: bar.width }" />
            </div>
            <span class="bar-value">{{ bar.value }}</span>
          </div>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card size="small" title="时间线预览">
          <a-spin :spinning="loadingTimelinePreview">
            <a-timeline v-if="timelinePreview.length">
              <a-timeline-item v-for="(event, idx) in timelinePreview" :key="idx">
                {{ formatTimelineDate(event.date) }} · {{ event.title }}
              </a-timeline-item>
            </a-timeline>
            <a-empty v-else description="暂无时间线事件" />
          </a-spin>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="8">
        <a-card size="small" title="今日用药执行">
          <div class="med-ring">
            <div>已服 {{ medicationSummary.today_taken }}</div>
            <div>跳过 {{ medicationSummary.today_skipped }}</div>
            <div>待执行 {{ medicationSummary.today_pending }}</div>
            <div>依从率 {{ medicationSummary.adherence_rate }}%</div>
          </div>
        </a-card>
      </a-col>
      <a-col :span="8">
        <a-card size="small" title="附件识别状态">
          <a-progress
            :percent="recognitionPercent"
            :success="{ percent: recognitionPercent }"
            status="active"
          />
          <div class="sub-text">AI 识别 {{ overview?.ai_task_summary?.ai_recognition_count ?? 0 }} · 附件 {{ overview?.ai_task_summary?.attachment_total ?? 0 }}</div>
        </a-card>
      </a-col>
      <a-col :span="8">
        <a-card size="small" title="异常数据">
          <a-spin :spinning="loadingQualityFlags">
            <a-alert
              v-for="flag in qualityFlagsPreview"
              :key="`${flag.type}-${flag.resource_id}`"
              type="warning"
              :message="flag.message"
              show-icon
              style="margin-bottom: 8px"
            />
            <a-empty v-if="!qualityFlagsPreview.length && !overview?.quality_flag_count" description="暂无异常" />
            <div v-else-if="(overview?.quality_flag_count || 0) > qualityFlagsPreview.length" class="sub-text">
              共 {{ overview?.quality_flag_count }} 条异常，切换至时间线旁查看详情
            </div>
          </a-spin>
        </a-card>
      </a-col>
    </a-row>
  </a-spin>

  <a-tabs v-model:activeKey="activeTab" @change="onTabChange">
    <a-tab-pane v-for="tab in tabs" :key="tab.key" :tab="tab.label" />
  </a-tabs>

  <div v-if="activeTab === 'overview'" class="tab-panel">
    <a-descriptions bordered size="small" :column="2">
      <a-descriptions-item v-for="item in overviewItems" :key="item.label" :label="item.label">
        {{ item.value }}
      </a-descriptions-item>
    </a-descriptions>
    <div style="margin-top: 16px">
      <div class="section-title">共享关系</div>
      <a-spin :spinning="loadingSharedRelations">
        <a-table :data-source="sharedRelations" row-key="binding_id" size="small" :pagination="false">
          <a-table-column title="用户" data-index="username" />
          <a-table-column title="关系" data-index="relationship_label" />
          <a-table-column title="权限" data-index="role_label" />
          <a-table-column title="状态" data-index="status_label" />
        </a-table>
      </a-spin>
    </div>
  </div>

  <div v-else-if="activeTab === 'timeline'" class="tab-panel">
    <a-spin :spinning="loadingTimeline">
      <a-timeline>
        <a-timeline-item v-for="(event, idx) in timelineRows" :key="idx">
          <strong>{{ formatTimelineDate(event.date) }}</strong> — {{ event.title }}
          <a-tag style="margin-left: 8px">{{ event.type }}</a-tag>
        </a-timeline-item>
      </a-timeline>
      <a-pagination
        style="margin-top: 16px; text-align: right"
        :current="timelineQuery.page"
        :page-size="timelineQuery.page_size"
        :total="timelinePagination.total"
        @change="onTimelinePageChange"
      />
    </a-spin>
  </div>

  <div v-else class="tab-panel">
    <a-space style="margin-bottom: 12px">
      <a-input-search
        v-model:value="resourceKeyword"
        placeholder="搜索"
        enter-button
        @search="debouncedResourceSearch"
        @change="debouncedResourceSearch"
        style="width: 260px"
      />
    </a-space>
    <a-table
      :data-source="resourceRows"
      :row-key="rowKey"
      :loading="loadingResources"
      :pagination="false"
      :scroll="{ x: 1400 }"
    >
      <a-table-column
        v-for="col in tableColumns"
        :key="col.key"
        :title="col.title"
        :data-index="col.dataIndex"
        :width="col.width"
      >
        <template v-if="col.key === 'updated_at'" #default="{ record }">
          {{ formatDateTime(record.updated_at) }}
        </template>
        <template v-else-if="col.key === 'exam_date' || col.key === 'performed_at' || col.key === 'prescribed_at' || col.key === 'scheduled_at'" #default="{ record }">
          {{ formatDateTime(record[col.key]) }}
        </template>
        <template v-else-if="col.key === 'expired'" #default="{ record }">
          <a-tag v-if="record.expired" color="red">已过期</a-tag>
          <a-tag v-else-if="record.expiring_soon" color="orange">临期</a-tag>
          <span v-else>-</span>
        </template>
      </a-table-column>
      <a-table-column title="操作" key="actions" :width="120" fixed="right">
        <template #default="{ record }">
          <a-button size="small" type="link" @click="openDetail(record.id)">详情</a-button>
        </template>
      </a-table-column>
    </a-table>
    <a-pagination
      style="margin-top: 16px; text-align: right"
      :current="resourceQuery.page"
      :page-size="resourceQuery.page_size"
      :total="resourcePagination.total"
      @change="onResourcePageChange"
    />
  </div>

  <MedicalDataDetailDrawer
    v-model:open="drawer.open"
    :loading="drawer.loading"
    :detail="drawer.detail"
    :title="drawer.title"
    :can-download="permissions.can_download_attachment"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { message } from 'ant-design-vue';
import MedicalDataDetailDrawer from '../components/medical/MedicalDataDetailDrawer.vue';
import {
  fetchMedicalDataComplete,
  fetchMedicalDataQualityFlags,
  fetchMedicalDataResourceDetail,
  fetchMedicalDataResources,
  fetchMedicalDataSharedRelations,
  fetchMedicalDataTimeline,
  MEDICAL_RESOURCE_TABS,
  type MedicalDataCompleteResponse,
  type MedicalDataPermissions,
  type MedicalDataQualityFlag,
  type MedicalDataResourceDetail,
  type MedicalDataSharedRelation,
  type MedicalDataTimelineEvent,
  type MedicalResourceType,
} from '../api/modules/medicalData';
import type { Pagination } from '../types';
import { formatDateTime } from '../utils/datetime';
import { displayGender } from '../utils/memberLabels';
import { useDebouncedFn } from '../utils/useDebouncedFn';

const route = useRoute();
const userId = Number(route.params.userId);
const memberId = Number(route.params.memberId);

const tabs = MEDICAL_RESOURCE_TABS;
const activeTab = ref<string>('overview');
const loadingOverview = ref(false);
const loadingResources = ref(false);
const loadingTimelinePreview = ref(false);
const loadingTimeline = ref(false);
const loadingQualityFlags = ref(false);
const loadingSharedRelations = ref(false);
const overview = ref<MedicalDataCompleteResponse | null>(null);
const timelinePreview = ref<MedicalDataTimelineEvent[]>([]);
const timelineRows = ref<MedicalDataTimelineEvent[]>([]);
const qualityFlagsPreview = ref<MedicalDataQualityFlag[]>([]);
const sharedRelations = ref<MedicalDataSharedRelation[]>([]);
const timelineQuery = reactive({ page: 1, page_size: 20 });
const timelinePagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

let resourceAbort: AbortController | null = null;
const permissions = reactive<MedicalDataPermissions>({
  can_view_sensitive: false,
  can_view_raw_json: false,
  can_view_attachment: false,
  can_download_attachment: false,
});

const resourceRows = ref<Record<string, unknown>[]>([]);
const resourceKeyword = ref('');
const resourceQuery = reactive({ page: 1, page_size: 20 });
const resourcePagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const drawer = reactive<{
  open: boolean;
  loading: boolean;
  detail: MedicalDataResourceDetail | null;
  title: string;
}>({ open: false, loading: false, detail: null, title: '' });

const medicationSummary = computed(() => overview.value?.medication_summary || {
  today_total: 0,
  today_taken: 0,
  today_skipped: 0,
  today_pending: 0,
  adherence_rate: 0,
});

const statCards = computed(() => {
  const counts = overview.value?.category_counts || {};
  return [
    { key: 'cases', label: '病例', value: counts.medical_cases || 0 },
    { key: 'health', label: '体检', value: counts.health_exam_reports || 0 },
    { key: 'exam', label: '检查', value: counts.examination_reports || 0 },
    { key: 'box', label: '药盒', value: counts.medicine_boxes || 0 },
    { key: 'rx', label: '处方', value: counts.prescriptions || 0 },
    { key: 'plan', label: '用药计划', value: counts.medication_plans || 0 },
    { key: 'attach', label: '附件', value: counts.attachments || 0 },
    { key: 'flags', label: '异常', value: overview.value?.quality_flag_count || 0 },
  ];
});

const categoryBars = computed(() => {
  const counts = overview.value?.category_counts || {};
  const items = [
    { label: '病例', value: counts.medical_cases || 0 },
    { label: '体检', value: counts.health_exam_reports || 0 },
    { label: '检查', value: counts.examination_reports || 0 },
    { label: '药盒', value: counts.medicine_boxes || 0 },
    { label: '处方', value: counts.prescriptions || 0 },
    { label: '用药计划', value: counts.medication_plans || 0 },
  ];
  const max = Math.max(...items.map((item) => item.value), 1);
  return items.map((item) => ({ ...item, width: `${Math.round((item.value / max) * 100)}%` }));
});

const recognitionPercent = computed(() => {
  const summary = overview.value?.ai_task_summary;
  if (!summary?.attachment_total) return 0;
  return Math.min(100, Math.round(((summary.completed || 0) / summary.attachment_total) * 100));
});

const overviewItems = computed(() => {
  const source = overview.value?.source_summary || {};
  return [
    { label: '手动录入', value: source.manual ?? 0 },
    { label: 'AI 识别', value: source.ai ?? 0 },
    { label: '附件总数', value: overview.value?.category_counts?.attachments ?? 0 },
    { label: '异常数', value: overview.value?.quality_flag_count ?? 0 },
  ];
});

const COLUMN_MAP: Record<string, Array<{ key: string; title: string; dataIndex?: string; width?: number }>> = {
  'medical-cases': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'title', title: '标题', dataIndex: 'title' },
    { key: 'diagnosis', title: '诊断', dataIndex: 'diagnosis' },
    { key: 'source', title: '来源', dataIndex: 'source', width: 100 },
    { key: 'attachment_count', title: '附件', dataIndex: 'attachment_count', width: 80 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'health-exam-reports': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'title', title: '报告', dataIndex: 'title' },
    { key: 'exam_date', title: '体检日期', width: 120 },
    { key: 'detail_count', title: '明细', dataIndex: 'detail_count', width: 80 },
    { key: 'source', title: '来源', dataIndex: 'source', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'examination-reports': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'title', title: '标题', dataIndex: 'title' },
    { key: 'category', title: '类型', dataIndex: 'category', width: 100 },
    { key: 'performed_at', title: '检查日期', width: 120 },
    { key: 'abnormal_count', title: '异常项', dataIndex: 'abnormal_count', width: 80 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'medicine-boxes': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'medicine_name', title: '药名', dataIndex: 'medicine_name' },
    { key: 'strength', title: '规格', dataIndex: 'strength', width: 120 },
    { key: 'expired', title: '有效期', width: 100 },
    { key: 'scope', title: '范围', dataIndex: 'scope', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'family-medicine-boxes': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'medicine_name', title: '药名', dataIndex: 'medicine_name' },
    { key: 'strength', title: '规格', dataIndex: 'strength', width: 120 },
    { key: 'expired', title: '有效期', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  prescriptions: [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'institution_name', title: '机构', dataIndex: 'institution_name' },
    { key: 'prescriber_name', title: '医生', dataIndex: 'prescriber_name', width: 100 },
    { key: 'prescribed_at', title: '开方时间', width: 170 },
    { key: 'plan_count', title: '计划数', dataIndex: 'plan_count', width: 80 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'medication-plans': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'drug_name', title: '药品', dataIndex: 'drug_name' },
    { key: 'frequency_text', title: '频次', dataIndex: 'frequency_text', width: 120 },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'medication-records': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'scheduled_at', title: '计划时间', width: 170 },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100 },
    { key: 'planned_dose', title: '计划剂量', dataIndex: 'planned_dose', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  symptoms: [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'name', title: '症状', dataIndex: 'name' },
    { key: 'severity', title: '程度', dataIndex: 'severity', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  visits: [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'department', title: '科室', dataIndex: 'department' },
    { key: 'doctor_name', title: '医生', dataIndex: 'doctor_name', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  surgeries: [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'procedure_name', title: '手术', dataIndex: 'procedure_name' },
    { key: 'surgeon', title: '医生', dataIndex: 'surgeon', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  'follow-ups': [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'method', title: '方式', dataIndex: 'method', width: 100 },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
  attachments: [
    { key: 'id', title: 'ID', dataIndex: 'id', width: 80 },
    { key: 'original_name', title: '文件名', dataIndex: 'original_name' },
    { key: 'mime_type', title: '类型', dataIndex: 'mime_type', width: 120 },
    { key: 'business_type', title: '业务类型', dataIndex: 'business_type', width: 140 },
    { key: 'updated_at', title: '更新时间', width: 170 },
  ],
};

const tableColumns = computed(() => COLUMN_MAP[activeTab.value] || []);

function rowKey(record: Record<string, unknown>) {
  return String(record.id);
}

function formatTimelineDate(value: string) {
  if (!value) return '-';
  return formatDateTime(value);
}

async function loadOverview() {
  loadingOverview.value = true;
  try {
    const data = await fetchMedicalDataComplete(userId, memberId);
    overview.value = data;
    Object.assign(permissions, data.permissions);
    void loadTimelinePreview();
    void loadQualityFlagsPreview();
    void loadSharedRelations();
  } catch {
    message.error('加载成员总览失败');
  } finally {
    loadingOverview.value = false;
  }
}

async function loadTimelinePreview() {
  loadingTimelinePreview.value = true;
  try {
    const data = await fetchMedicalDataTimeline(userId, memberId, { page: 1, page_size: 5 });
    timelinePreview.value = data.items;
  } finally {
    loadingTimelinePreview.value = false;
  }
}

async function loadQualityFlagsPreview() {
  loadingQualityFlags.value = true;
  try {
    const data = await fetchMedicalDataQualityFlags(userId, memberId, { page: 1, page_size: 3 });
    qualityFlagsPreview.value = data.items;
  } finally {
    loadingQualityFlags.value = false;
  }
}

async function loadSharedRelations() {
  loadingSharedRelations.value = true;
  try {
    const data = await fetchMedicalDataSharedRelations(userId, memberId, false);
    sharedRelations.value = data.items;
  } finally {
    loadingSharedRelations.value = false;
  }
}

async function loadTimeline() {
  loadingTimeline.value = true;
  try {
    const data = await fetchMedicalDataTimeline(userId, memberId, { ...timelineQuery });
    timelineRows.value = data.items;
    Object.assign(timelinePagination, data.pagination);
  } catch {
    message.error('加载时间线失败');
  } finally {
    loadingTimeline.value = false;
  }
}

async function loadResources() {
  if (activeTab.value === 'overview' || activeTab.value === 'timeline') return;
  loadingResources.value = true;
  resourceAbort?.abort();
  resourceAbort = new AbortController();
  try {
    const data = await fetchMedicalDataResources(
      userId,
      memberId,
      activeTab.value as MedicalResourceType,
      { ...resourceQuery, keyword: resourceKeyword.value || undefined },
      { signal: resourceAbort.signal },
    );
    resourceRows.value = data.items;
    Object.assign(resourcePagination, data.pagination);
    Object.assign(permissions, data.permissions);
  } catch (err) {
    if ((err as Error).name === 'CanceledError') return;
    message.error('加载列表失败');
  } finally {
    loadingResources.value = false;
  }
}

const debouncedResourceSearch = useDebouncedFn(() => {
  resourceQuery.page = 1;
  loadResources();
}, 400);

function onTabChange() {
  resourceQuery.page = 1;
  if (activeTab.value === 'timeline') {
    loadTimeline();
    return;
  }
  if (activeTab.value !== 'overview') {
    loadResources();
  }
}

function onTimelinePageChange(page: number, pageSize: number) {
  timelineQuery.page = page;
  timelineQuery.page_size = pageSize;
  loadTimeline();
}

function onResourcePageChange(page: number, pageSize: number) {
  resourceQuery.page = page;
  resourceQuery.page_size = pageSize;
  loadResources();
}

async function openDetail(resourceId: number) {
  drawer.open = true;
  drawer.loading = true;
  drawer.title = `${activeTab.value} #${resourceId}`;
  try {
    drawer.detail = await fetchMedicalDataResourceDetail(activeTab.value, resourceId);
  } catch {
    message.error('加载详情失败');
    drawer.open = false;
  } finally {
    drawer.loading = false;
  }
}

onMounted(async () => {
  await loadOverview();
});

onUnmounted(() => resourceAbort?.abort());
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.section-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.bar-row {
  display: grid;
  grid-template-columns: 72px 1fr 36px;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.bar-track {
  background: #f0f0f0;
  border-radius: 4px;
  height: 10px;
  overflow: hidden;
}
.bar-fill {
  background: #1677ff;
  height: 100%;
}
.bar-label,
.bar-value {
  font-size: 12px;
}
.med-ring {
  display: grid;
  gap: 6px;
  font-size: 13px;
}
.sub-text {
  margin-top: 8px;
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}
.tab-panel {
  margin-top: 8px;
}
</style>
