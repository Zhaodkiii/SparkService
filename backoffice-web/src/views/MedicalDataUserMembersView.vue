<template>
  <div class="page-header">
    <a-breadcrumb>
      <a-breadcrumb-item><router-link to="/medical-data/users">医疗数据</router-link></a-breadcrumb-item>
      <a-breadcrumb-item>用户 {{ userId }}</a-breadcrumb-item>
    </a-breadcrumb>
  </div>

  <a-alert v-if="loadError" type="error" show-icon :message="loadError" style="margin-bottom: 12px">
    <template #action><a-button size="small" @click="load">重试</a-button></template>
  </a-alert>

  <a-spin :spinning="loading">
    <a-skeleton v-if="loading && !userSummary" active :paragraph="{ rows: 3 }" />
    <a-descriptions v-else-if="userSummary" bordered size="small" :column="4" style="margin-bottom: 16px">
      <a-descriptions-item label="用户 ID">{{ userSummary.user_id }}</a-descriptions-item>
      <a-descriptions-item label="用户名">{{ userSummary.username }}</a-descriptions-item>
      <a-descriptions-item label="邮箱">{{ userSummary.email || '-' }}</a-descriptions-item>
      <a-descriptions-item label="状态">
        <a-tag :color="userSummary.is_active ? 'green' : 'red'">{{ userSummary.user_status }}</a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="注册时间">{{ formatDateTime(userSummary.date_joined) }}</a-descriptions-item>
      <a-descriptions-item label="最近登录">{{ formatDateTime(userSummary.last_login) }}</a-descriptions-item>
      <a-descriptions-item label="成员数">
        {{ userSummary.member_count }}
        <span v-if="userSummary.members_with_data_count < userSummary.member_count" class="member-count-hint">
          （有医疗数据 {{ userSummary.members_with_data_count }}）
        </span>
      </a-descriptions-item>
      <a-descriptions-item label="医疗数据总数">{{ userSummary.medical_data_total }}</a-descriptions-item>
      <a-descriptions-item label="附件数">{{ userSummary.attachment_count }}</a-descriptions-item>
      <a-descriptions-item label="最近更新">{{ formatDateTime(userSummary.last_updated_at) }}</a-descriptions-item>
    </a-descriptions>

    <div class="section-header">
      <div class="section-title">成员列表</div>
      <a-checkbox v-model:checked="onlyWithData" @change="onOnlyWithDataChange">仅显示有医疗数据的成员</a-checkbox>
    </div>
    <a-table :data-source="members" row-key="member_id" :pagination="false" :scroll="{ x: 1800 }">
      <template #emptyText><a-empty description="该用户暂无家庭成员" /></template>
      <a-table-column title="成员 ID" data-index="member_id" :width="90" />
      <a-table-column title="姓名" key="name" :width="130">
        <template #default="{ record }">
          {{ record.name }}
          <a-tag v-if="!record.has_data" color="default" style="margin-left: 4px">无医疗数据</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="关系" data-index="relationship_label" :width="80" />
      <a-table-column title="性别" key="gender" :width="70">
        <template #default="{ record }">{{ displayGender(record) }}</template>
      </a-table-column>
      <a-table-column title="年龄" data-index="age" :width="60" />
      <a-table-column title="共享关系" data-index="share_summary" :width="100" />
      <a-table-column title="关联用户" data-index="shared_user_count" :width="90" />
      <a-table-column title="病例" data-index="medical_case_count" :width="70" />
      <a-table-column title="体检" data-index="health_exam_report_count" :width="70" />
      <a-table-column title="检查" data-index="examination_report_count" :width="70" />
      <a-table-column title="用药" key="medication" :width="90">
        <template #default="{ record }">
          {{ record.medication_plan_count }} / {{ record.medicine_box_count }}
        </template>
      </a-table-column>
      <a-table-column title="附件" data-index="attachment_count" :width="70" />
      <a-table-column title="最近更新" key="last_updated_at" :width="170">
        <template #default="{ record }">{{ formatDateTime(record.last_updated_at) }}</template>
      </a-table-column>
      <a-table-column title="操作" key="actions" :width="actionsColWidth" fixed="right">
        <template #default="{ record }">
          <TableHoverActions>
            <a-button size="small" type="primary" @click="openMember(record.member_id)">查看医疗数据</a-button>
            <a-button size="small" @click="showShare(record.member_id)">共享关系</a-button>
          </TableHoverActions>
        </template>
      </a-table-column>
    </a-table>

    <a-pagination
      style="margin-top: 16px; text-align: right"
      :current="memberQuery.page"
      :page-size="memberQuery.page_size"
      :total="pagination.total"
      @change="onMemberPageChange"
    />
  </a-spin>

  <a-modal v-model:open="shareModal.open" title="成员共享关系" width="900px" :footer="null">
    <a-table :data-source="shareModal.rows" row-key="binding_id" :pagination="false" size="small">
      <a-table-column title="用户 ID" data-index="user_id" :width="90" />
      <a-table-column title="用户" data-index="username" />
      <a-table-column title="邮箱" data-index="email" />
      <a-table-column title="成员关系" data-index="relationship_label" />
      <a-table-column title="权限" data-index="role_label" />
      <a-table-column title="状态" data-index="status_label" />
      <a-table-column title="绑定时间" key="created_at">
        <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
      </a-table-column>
    </a-table>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import TableHoverActions from '../components/TableHoverActions.vue';
import {
  fetchMedicalDataSharedRelations,
  fetchMedicalDataUserMembers,
  type MedicalDataMemberRow,
  type MedicalDataSharedRelation,
  type MedicalDataUserSummary,
} from '../api/modules/medicalData';
import type { Pagination } from '../types';
import { formatDateTime } from '../utils/datetime';
import { displayGender } from '../utils/memberLabels';
import { calcActionsColWidth } from '../utils/tableActionsWidth';

const route = useRoute();
const router = useRouter();
const userId = Number(route.params.userId);
const actionsColWidth = calcActionsColWidth({ buttons: 2 });

const loading = ref(false);
const loadError = ref('');
const userSummary = ref<MedicalDataUserSummary | null>(null);
const members = ref<MedicalDataMemberRow[]>([]);
const memberQuery = reactive({ page: 1, page_size: 20 });
const onlyWithData = ref(false);
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const shareModal = reactive<{ open: boolean; rows: MedicalDataSharedRelation[] }>({ open: false, rows: [] });

let abort: AbortController | null = null;

async function load() {
  loadError.value = '';
  loading.value = true;
  abort?.abort();
  abort = new AbortController();
  try {
    const params: { page: number; page_size: number; only_with_data?: string } = { ...memberQuery };
    if (onlyWithData.value) {
      params.only_with_data = 'true';
    }
    const data = await fetchMedicalDataUserMembers(userId, params, { signal: abort.signal });
    userSummary.value = data.user;
    members.value = data.members;
    Object.assign(pagination, data.pagination);
  } catch (err) {
    if ((err as Error).name === 'CanceledError') return;
    loadError.value = (err as Error).message || '加载失败';
    message.error(loadError.value);
  } finally {
    loading.value = false;
  }
}

function onOnlyWithDataChange() {
  memberQuery.page = 1;
  load();
}

function onMemberPageChange(page: number, pageSize: number) {
  memberQuery.page = page;
  memberQuery.page_size = pageSize;
  load();
}

function openMember(memberId: number) {
  router.push(`/medical-data/users/${userId}/members/${memberId}`);
}

async function showShare(memberId: number) {
  try {
    const data = await fetchMedicalDataSharedRelations(userId, memberId, true);
    shareModal.rows = data.items;
    shareModal.open = true;
  } catch {
    message.error('加载共享关系失败');
  }
}

onMounted(load);
onUnmounted(() => abort?.abort());
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title {
  font-weight: 600;
}
.member-count-hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}
</style>
