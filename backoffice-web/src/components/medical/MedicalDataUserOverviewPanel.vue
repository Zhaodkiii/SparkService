<template>
  <div :class="['medical-user-overview', { 'medical-user-overview--embedded': embedded }]">
    <div class="medical-user-overview__header">
      <a-breadcrumb>
        <a-breadcrumb-item>医疗数据</a-breadcrumb-item>
        <a-breadcrumb-item>用户 {{ userId }}</a-breadcrumb-item>
      </a-breadcrumb>
      <div class="medical-user-overview__actions">
        <a-button size="small" @click="router.push(`/medical-data/users/${userId}`)">打开医疗数据页</a-button>
        <a-button v-if="closable" size="small" @click="emit('close')">收起</a-button>
      </div>
    </div>

    <a-alert v-if="loadError" type="error" show-icon :message="loadError" style="margin-bottom: 12px">
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>

    <a-spin :spinning="loading">
      <a-skeleton v-if="loading && !userSummary" active :paragraph="{ rows: 3 }" />
      <template v-else-if="userSummary">
        <a-descriptions bordered size="small" :column="4" style="margin-bottom: 16px">
          <a-descriptions-item label="用户 ID">{{ userSummary.user_id }}</a-descriptions-item>
          <a-descriptions-item label="用户名">{{ userSummary.username }}</a-descriptions-item>
          <a-descriptions-item label="邮箱">{{ userSummary.email || '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="userSummary.is_active ? 'green' : 'red'">{{ userSummary.user_status }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="注册时间">{{ formatDateTime(userSummary.date_joined) }}</a-descriptions-item>
          <a-descriptions-item label="最近登录">{{ formatDateTime(userSummary.last_login) }}</a-descriptions-item>
          <a-descriptions-item label="成员数">{{ userSummary.member_count }}</a-descriptions-item>
          <a-descriptions-item label="医疗数据总数">{{ userSummary.medical_data_total }}</a-descriptions-item>
          <a-descriptions-item label="附件数">{{ userSummary.attachment_count }}</a-descriptions-item>
          <a-descriptions-item label="最近更新">{{ formatDateTime(userSummary.last_updated_at) }}</a-descriptions-item>
        </a-descriptions>

        <div class="section-title">成员列表</div>
        <a-table :data-source="members" row-key="member_id" :pagination="false" :scroll="{ x: 1800 }" size="small">
          <template #emptyText><a-empty description="该用户暂无成员医疗数据" /></template>
          <a-table-column title="成员 ID" data-index="member_id" :width="90" />
          <a-table-column title="姓名" data-index="name" :width="100" />
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
          v-if="pagination.total > memberQuery.page_size"
          style="margin-top: 16px; text-align: right"
          :current="memberQuery.page"
          :page-size="memberQuery.page_size"
          :total="pagination.total"
          @change="onMemberPageChange"
        />
      </template>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import TableHoverActions from '../TableHoverActions.vue';
import {
  fetchMedicalDataSharedRelations,
  fetchMedicalDataUserMembers,
  type MedicalDataMemberRow,
  type MedicalDataSharedRelation,
  type MedicalDataUserSummary,
} from '../../api/modules/medicalData';
import type { Pagination } from '../../types';
import { formatDateTime } from '../../utils/datetime';
import { displayGender } from '../../utils/memberLabels';
import { calcActionsColWidth } from '../../utils/tableActionsWidth';

const props = withDefaults(
  defineProps<{
    userId: number;
    active?: boolean;
    closable?: boolean;
    embedded?: boolean;
  }>(),
  {
    active: true,
    closable: false,
    embedded: false,
  },
);

const emit = defineEmits<{ close: [] }>();

const router = useRouter();
const actionsColWidth = calcActionsColWidth({ buttons: 2 });

const loading = ref(false);
const loadError = ref('');
const userSummary = ref<MedicalDataUserSummary | null>(null);
const members = ref<MedicalDataMemberRow[]>([]);
const memberQuery = reactive({ page: 1, page_size: 20 });
const pagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const shareModal = reactive<{ open: boolean; rows: MedicalDataSharedRelation[] }>({ open: false, rows: [] });

let abort: AbortController | null = null;

async function load() {
  if (!props.userId || !props.active) return;
  loadError.value = '';
  loading.value = true;
  abort?.abort();
  abort = new AbortController();
  try {
    const data = await fetchMedicalDataUserMembers(props.userId, { ...memberQuery }, { signal: abort.signal });
    userSummary.value = data.user;
    members.value = data.members;
    Object.assign(pagination, data.pagination);
  } catch (err) {
    if ((err as Error).name === 'CanceledError' || String((err as Error).message || '').toLowerCase().includes('cancel')) {
      return;
    }
    loadError.value = (err as Error).message || '加载失败';
  } finally {
    loading.value = false;
  }
}

function onMemberPageChange(page: number, pageSize: number) {
  memberQuery.page = page;
  memberQuery.page_size = pageSize;
  load();
}

function openMember(memberId: number) {
  router.push(`/medical-data/users/${props.userId}/members/${memberId}`);
}

async function showShare(memberId: number) {
  try {
    const data = await fetchMedicalDataSharedRelations(props.userId, memberId, true);
    shareModal.rows = data.items;
    shareModal.open = true;
  } catch {
    message.error('加载共享关系失败');
  }
}

watch(
  () => [props.userId, props.active] as const,
  ([userId, active]) => {
    if (userId && active) {
      memberQuery.page = 1;
      load();
    }
  },
  { immediate: true },
);

onMounted(() => {
  if (props.active) {
    load();
  }
});

onUnmounted(() => abort?.abort());
</script>

<style scoped>
.medical-user-overview {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px 16px 16px;
  margin-bottom: 16px;
  background: #fff;
}
.medical-user-overview__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.medical-user-overview__actions {
  display: flex;
  gap: 8px;
}
.medical-user-overview--embedded {
  border: none;
  border-radius: 0;
  padding: 0;
  margin-bottom: 0;
  background: transparent;
}
.section-title {
  font-weight: 600;
  margin-bottom: 8px;
}
</style>
