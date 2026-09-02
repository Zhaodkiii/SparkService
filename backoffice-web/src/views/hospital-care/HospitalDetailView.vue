<template>
  <a-spin :spinning="loading">
    <a-alert v-if="errorText" type="error" show-icon :message="errorText" style="margin-bottom: 16px">
      <template #action>
        <a-button size="small" @click="loadHospital">重试</a-button>
      </template>
    </a-alert>

    <template v-if="hospital">
      <div v-if="!isStandalone" style="display: flex; justify-content: space-between; gap: 16px; margin-bottom: 16px; flex-wrap: wrap">
        <a-space align="start" :size="16">
          <a-button @click="router.push('/hospital-care/hospitals')">医院列表</a-button>
          <div>
            <a-space>
              <a-typography-title :level="4" style="margin: 0">{{ hospital.name }}</a-typography-title>
              <a-typography-text type="secondary">{{ hospital.code }}</a-typography-text>
              <a-tag :color="HOSPITAL_STATUS_COLOR[hospital.status]">{{ HOSPITAL_STATUS_LABEL[hospital.status] }}</a-tag>
            </a-space>
            <div style="color: #8c8c8c; margin-top: 4px">
              {{ regionText(hospital) }} · {{ SERVICE_MODE_LABEL[hospital.service_mode] }}
            </div>
          </div>
        </a-space>
        <a-space>
          <a-button
            v-if="canActivate && hospital.status !== 'active'"
            type="primary"
            :loading="statusSaving"
            @click="onActivate"
          >
            启用服务
          </a-button>
          <a-button v-if="canSuspend && hospital.status === 'active'" danger :loading="statusSaving" @click="openSuspend">
            暂停服务
          </a-button>
        </a-space>
      </div>

      <div v-if="isStandalone" class="standalone-section-heading">
        <div>
          <h2>{{ currentTabTitle }}</h2>
          <p>{{ currentTabDescription }}</p>
        </div>
        <a-tag v-if="displayedTab === 'overview'" color="blue">当前医院</a-tag>
      </div>

      <a-tabs :active-key="displayedTab" :tab-bar-style="isStandalone ? { display: 'none' } : undefined" class="hospital-detail-tabs" @change="onTabChange">
        <a-tab-pane key="overview" tab="概览">
          <div class="overview-metrics">
            <div class="overview-metric">
              <span>科室</span>
              <strong>{{ overview.department_count }}</strong>
              <small>已配置科室</small>
            </div>
            <div class="overview-metric">
              <span>有效医生</span>
              <strong>{{ overview.doctor_count }}</strong>
              <small>可参与医院服务</small>
            </div>
            <div class="overview-metric overview-metric-accent">
              <span>已发布智能体</span>
              <strong>{{ overview.published_agent_count }}</strong>
              <small>患者端可见</small>
            </div>
            <div class="overview-metric">
              <span>进行中会话</span>
              <strong>{{ overview.active_conversation_count }}</strong>
              <small>当前服务中</small>
            </div>
          </div>
          <div class="overview-grid">
            <a-card title="待处理事项" size="small" class="overview-card">
              <ul class="pending-list">
                <li v-if="overview.pending_license_count">{{ overview.pending_license_count }} 位医生资质待核验</li>
                <li v-if="overview.pending_review_agent_count">{{ overview.pending_review_agent_count }} 个智能体待审核</li>
                <li v-if="hospital.service_mode === 'demo'">挂号模式为 Demo，尚未接入真实号源</li>
                <li v-if="!pendingItems">暂无待处理事项</li>
              </ul>
            </a-card>
            <a-card title="最近操作" size="small" class="overview-card overview-audit-card">
            <a-table :data-source="recentAudit" row-key="id" size="small" :pagination="false">
              <a-table-column title="时间" key="created_at" :width="180">
                <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
              </a-table-column>
              <a-table-column title="操作人" data-index="user_id" :width="100" />
              <a-table-column title="动作" data-index="action" />
              <a-table-column title="Request ID" data-index="request_id" />
            </a-table>
            </a-card>
          </div>
        </a-tab-pane>

        <a-tab-pane key="base" tab="基础资料">
          <HospitalBaseInfoForm :form="baseForm" mode="edit" :disabled="!editingBase" />
          <div style="text-align: right">
            <a-space v-if="canUpdate">
              <template v-if="editingBase">
                <a-button @click="cancelEditBase">取消</a-button>
                <a-button type="primary" :loading="baseSaving" @click="saveBase">保存</a-button>
              </template>
              <a-button v-else type="primary" @click="editingBase = true">编辑</a-button>
            </a-space>
          </div>
        </a-tab-pane>

        <a-tab-pane key="departments" tab="科室">
          <a-space wrap style="margin-bottom: 16px">
            <a-input-search v-model:value="departmentQuery.q" placeholder="搜索科室" style="width: 220px" @search="loadDepartments" />
            <a-select v-model:value="departmentQuery.status" style="width: 140px" @change="loadDepartments">
              <a-select-option value="">全部状态</a-select-option>
              <a-select-option value="active">启用</a-select-option>
              <a-select-option value="hidden">隐藏</a-select-option>
            </a-select>
            <a-button v-if="canUpdateDept" type="primary" @click="openDepartment()">新增科室</a-button>
          </a-space>
          <a-table :data-source="departments" row-key="id" :pagination="false" :loading="deptLoading">
            <a-table-column title="科室名称" data-index="name" />
            <a-table-column title="编码" data-index="code" :width="120" />
            <a-table-column title="上级科室" key="parent" :width="140">
              <template #default="{ record }">{{ parentName(record.parent_id) }}</template>
            </a-table-column>
            <a-table-column title="医生数" data-index="doctor_count" :width="90" />
            <a-table-column title="智能体数" data-index="agent_count" :width="100" />
            <a-table-column title="状态" key="status" :width="90">
              <template #default="{ record }">
                <a-tag :color="record.status === 'active' ? 'green' : 'default'">{{ departmentStatusLabel(record.status) }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column v-if="canUpdateDept" title="操作" key="actions" :width="100">
              <template #default="{ record }">
                <a-button size="small" @click="openDepartment(record)">编辑</a-button>
              </template>
            </a-table-column>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="people" tab="职工与医生">
          <a-tabs v-model:activeKey="peopleTab">
            <a-tab-pane key="staff" tab="职工">
              <a-space wrap style="margin-bottom: 16px">
                <a-input-search v-model:value="staffQuery.q" placeholder="搜索姓名 / 工号 / 账号" style="width: 240px" @search="loadStaff" />
                <a-button v-if="canInvite" type="primary" @click="openInvite">邀请职工</a-button>
              </a-space>
              <a-table :data-source="staffRows" row-key="id" :pagination="false" :loading="staffLoading">
                <a-table-column title="姓名" data-index="display_name" />
                <a-table-column title="工号" data-index="employee_no" :width="120" />
                <a-table-column title="角色" key="role" :width="130">
                  <template #default="{ record }">{{ staffRoleLabel(record.role) }}</template>
                </a-table-column>
                <a-table-column title="账号" data-index="username" />
                <a-table-column title="资质状态" key="license" :width="110">
                  <template #default="{ record }">{{ record.license_status ? licenseLabel(record.license_status) : '--' }}</template>
                </a-table-column>
                <a-table-column title="账号状态" key="status" :width="100">
                  <template #default="{ record }">{{ staffStatusLabel(record.status) }}</template>
                </a-table-column>
                <a-table-column v-if="canUpdateStaff" title="操作" key="actions" :width="100">
                  <template #default="{ record }">
                    <a-button size="small" @click="openStaff(record)">编辑</a-button>
                  </template>
                </a-table-column>
              </a-table>
              <a-pagination
                style="margin-top: 16px; text-align: right"
                :current="staffQuery.page"
                :page-size="staffQuery.page_size"
                :total="staffPagination.total"
                @change="onStaffPage"
              />
            </a-tab-pane>
            <a-tab-pane key="doctors" tab="医生资料">
              <a-space wrap style="margin-bottom: 16px">
                <a-input-search v-model:value="doctorQuery.q" placeholder="搜索医生" style="width: 220px" @search="loadDoctors" />
              </a-space>
              <a-table :data-source="doctorRows" row-key="id" :pagination="false" :loading="doctorLoading">
                <a-table-column title="姓名" data-index="display_name" />
                <a-table-column title="职称" data-index="title" />
                <a-table-column title="擅长" key="specialties">
                  <template #default="{ record }">{{ (record.specialties || []).join('、') || '--' }}</template>
                </a-table-column>
                <a-table-column title="资质状态" key="license" :width="110">
                  <template #default="{ record }">{{ licenseLabel(record.license_status) }}</template>
                </a-table-column>
                <a-table-column title="展示状态" key="profile" :width="110">
                  <template #default="{ record }">{{ doctorProfileStatusLabel(record.profile_status) }}</template>
                </a-table-column>
                <a-table-column v-if="canUpdateDoctor" title="操作" key="actions" :width="100">
                  <template #default="{ record }">
                    <a-button size="small" @click="openDoctor(record)">编辑</a-button>
                  </template>
                </a-table-column>
              </a-table>
              <a-pagination
                style="margin-top: 16px; text-align: right"
                :current="doctorQuery.page"
                :page-size="doctorQuery.page_size"
                :total="doctorPagination.total"
                @change="onDoctorPage"
              />
            </a-tab-pane>
          </a-tabs>
        </a-tab-pane>

        <a-tab-pane key="agents" tab="智能体">
          <a-space wrap style="margin-bottom: 16px">
            <a-input-search v-model:value="agentQuery.q" placeholder="搜索智能体 / 医生" style="width: 240px" @search="loadAgents" />
            <a-select v-model:value="agentQuery.status" style="width: 140px" @change="loadAgents">
              <a-select-option value="">全部状态</a-select-option>
              <a-select-option value="review">待审核</a-select-option>
              <a-select-option value="published">已发布</a-select-option>
              <a-select-option value="draft">草稿</a-select-option>
              <a-select-option value="disabled">已暂停</a-select-option>
            </a-select>
            <a-select v-model:value="agentQuery.department_id" style="width: 180px" allow-clear placeholder="科室" @change="loadAgents">
              <a-select-option v-for="item in departments" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
            </a-select>
            <a-button v-if="canCreateAgent" type="primary" @click="openAgentForm()">+ 新建智能体</a-button>
          </a-space>
          <a-table :data-source="agentRows" row-key="id" :pagination="false" :loading="agentLoading">
            <a-table-column title="智能体名称" data-index="name" />
            <a-table-column title="医生" key="doctor" :width="120">
              <template #default="{ record }">{{ record.doctor?.display_name || '--' }}</template>
            </a-table-column>
            <a-table-column title="科室" key="department" :width="140">
              <template #default="{ record }">{{ record.department?.name || '--' }}</template>
            </a-table-column>
            <a-table-column title="知识库" key="kb" :width="90">
              <template #default="{ record }">{{ record.knowledge_bindings?.length ?? 0 }} 个</template>
            </a-table-column>
            <a-table-column title="发布状态" key="status" :width="110">
              <template #default="{ record }">
                <a-tag :color="agentStatusColor(record.publication_status)">{{ agentStatusLabel(record.publication_status) }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column v-if="canReview || canCreateAgent || canUpdateAgent" title="操作" key="actions" :width="220">
              <template #default="{ record }">
                <TableHoverActions>
                  <a-button v-if="canUpdateAgent || canCreateAgent" size="small" @click="openAgentForm(record)">维护</a-button>
                  <a-button v-if="canReview && record.publication_status === 'review'" size="small" type="primary" @click="openReview(record, 'publish')">
                    通过
                  </a-button>
                  <a-button v-if="canReview && record.publication_status === 'review'" size="small" danger @click="openReview(record, 'reject')">
                    驳回
                  </a-button>
                  <a-button v-if="canReview && record.publication_status === 'published'" size="small" @click="openReview(record, 'disable')">
                    暂停
                  </a-button>
                </TableHoverActions>
              </template>
            </a-table-column>
          </a-table>
          <a-pagination
            style="margin-top: 16px; text-align: right"
            :current="agentQuery.page"
            :page-size="agentQuery.page_size"
            :total="agentPagination.total"
            @change="onAgentPage"
          />
        </a-tab-pane>

        <a-tab-pane key="knowledge" tab="知识库">
          <HospitalKnowledgeTab
            :hospital-id="hospitalId"
            :departments="departments"
            :can-create="canCreateKnowledge"
            :can-update="canUpdateKnowledge"
            :can-delete="canDeleteKnowledge"
            :can-build="canBuildKnowledge"
          />
        </a-tab-pane>

        <a-tab-pane key="integration" tab="服务接入">
          <a-descriptions bordered :column="1" size="small">
            <a-descriptions-item label="挂号与就医模式">{{ SERVICE_MODE_LABEL[hospital.service_mode] }}</a-descriptions-item>
            <a-descriptions-item v-if="hospital.service_mode === 'redirect'" label="官方跳转地址">
              {{ hospital.registration_redirect_url || '--' }}
            </a-descriptions-item>
            <a-descriptions-item label="HIS 接入状态">
              {{ hospital.service_mode === 'integrated' ? '未配置，当前不能启用' : '未使用 HIS 接入' }}
            </a-descriptions-item>
          </a-descriptions>
          <a-alert
            style="margin-top: 16px"
            type="info"
            show-icon
            message="密钥、签名 Secret 和生产凭证不返回前端明文。Demo 模式不会显示真实接入成功。"
          />
        </a-tab-pane>

        <a-tab-pane key="audit" tab="审计记录">
          <a-space wrap style="margin-bottom: 16px">
            <a-input v-model:value="auditQuery.action" placeholder="动作类型，例如 hospital.update" style="width: 260px" allow-clear />
            <a-button type="primary" @click="loadAudit">查询</a-button>
          </a-space>
          <a-table :data-source="auditRows" row-key="id" :pagination="false" :loading="auditLoading">
            <a-table-column title="时间" key="created_at" :width="180">
              <template #default="{ record }">{{ formatDateTime(record.created_at) }}</template>
            </a-table-column>
            <a-table-column title="操作人" data-index="user_id" :width="100" />
            <a-table-column title="动作" data-index="action" />
            <a-table-column title="结果" key="status" :width="90">
              <template #default="{ record }">
                <a-tag :color="record.status_code < 400 ? 'green' : 'red'">{{ record.status_code < 400 ? '成功' : '失败' }}</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="Request ID" data-index="request_id" />
          </a-table>
          <a-pagination
            style="margin-top: 16px; text-align: right"
            :current="auditQuery.page"
            :page-size="auditQuery.page_size"
            :total="auditPagination.total"
            @change="onAuditPage"
          />
        </a-tab-pane>
      </a-tabs>
    </template>

    <a-modal v-model:open="deptModal.open" :title="deptModal.isCreate ? '新增科室' : '编辑科室'" :confirm-loading="deptModal.saving" @ok="submitDepartment">
      <a-form layout="vertical">
        <a-form-item v-if="deptModal.isCreate" label="科室编码" required>
          <a-input v-model:value="deptModal.form.code" />
        </a-form-item>
        <a-form-item label="科室名称" required>
          <a-input v-model:value="deptModal.form.name" />
        </a-form-item>
        <a-form-item label="简称">
          <a-input v-model:value="deptModal.form.short_name" />
        </a-form-item>
        <a-form-item label="上级科室">
          <a-select v-model:value="deptModal.form.parent_id" allow-clear placeholder="无">
            <a-select-option v-for="item in parentOptions" :key="item.id" :value="item.id">{{ item.name }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="排序">
          <a-input-number v-model:value="deptModal.form.sort_order" style="width: 100%" />
        </a-form-item>
        <a-form-item label="状态">
          <a-select v-model:value="deptModal.form.status">
            <a-select-option value="active">启用</a-select-option>
            <a-select-option value="hidden">隐藏</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="deptModal.form.description" :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="inviteModal.open" title="邀请职工" :confirm-loading="inviteModal.saving" @ok="submitInvite">
      <a-form layout="vertical">
        <a-form-item label="用户账号" required>
          <a-select
            v-model:value="inviteModal.form.user_id"
            show-search
            :filter-option="false"
            :options="userOptions"
            placeholder="输入账号或显示名称搜索"
            @search="onUserSearch"
          />
        </a-form-item>
        <a-form-item label="角色" required>
          <a-select v-model:value="inviteModal.form.role">
            <a-select-option value="hospital_admin">医院管理员</a-select-option>
            <a-select-option value="doctor">医生</a-select-option>
            <a-select-option value="nurse">护士</a-select-option>
            <a-select-option value="auditor">审计员</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="工号">
          <a-input v-model:value="inviteModal.form.employee_no" />
        </a-form-item>
        <a-form-item label="账号状态">
          <a-select v-model:value="inviteModal.form.status">
            <a-select-option value="invited">已邀请</a-select-option>
            <a-select-option value="active">有效</a-select-option>
          </a-select>
        </a-form-item>
        <template v-if="inviteModal.form.role === 'doctor'">
          <a-form-item label="医生姓名">
            <a-input v-model:value="inviteModal.form.display_name" />
          </a-form-item>
          <a-form-item label="职称">
            <a-input v-model:value="inviteModal.form.title" />
          </a-form-item>
        </template>
      </a-form>
    </a-modal>

    <a-modal v-model:open="staffModal.open" title="编辑职工" :confirm-loading="staffModal.saving" @ok="submitStaff">
      <a-form layout="vertical">
        <a-form-item label="账号">
          <a-input :value="staffModal.username" disabled />
        </a-form-item>
        <a-form-item label="角色" required>
          <a-select v-model:value="staffModal.form.role" :disabled="staffModal.lockedRole">
            <a-select-option value="hospital_admin">医院管理员</a-select-option>
            <a-select-option value="doctor">医生</a-select-option>
            <a-select-option value="nurse">护士</a-select-option>
            <a-select-option value="auditor">审计员</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="工号">
          <a-input v-model:value="staffModal.form.employee_no" />
        </a-form-item>
        <a-form-item label="账号状态">
          <a-select v-model:value="staffModal.form.status">
            <a-select-option value="invited">已邀请</a-select-option>
            <a-select-option value="active">有效</a-select-option>
            <a-select-option value="suspended">已暂停</a-select-option>
          </a-select>
        </a-form-item>
        <template v-if="staffModal.form.role === 'doctor' && !staffModal.lockedRole">
          <a-form-item label="医生姓名">
            <a-input v-model:value="staffModal.form.display_name" />
          </a-form-item>
          <a-form-item label="职称">
            <a-input v-model:value="staffModal.form.title" />
          </a-form-item>
        </template>
        <p v-else-if="staffModal.lockedRole" style="margin: 0; color: rgba(0, 0, 0, 0.45)">资质与展示状态请到「医生资料」编辑。</p>
      </a-form>
    </a-modal>

    <a-modal v-model:open="reasonModal.open" :title="reasonModal.title" :confirm-loading="reasonModal.saving" @ok="submitReason">
      <p v-if="reasonModal.description" style="margin-bottom: 12px">{{ reasonModal.description }}</p>
      <a-textarea v-model:value="reasonModal.reason" :rows="4" placeholder="请填写原因" />
    </a-modal>

    <a-modal v-model:open="doctorModal.open" title="编辑医生资料" :confirm-loading="doctorModal.saving" @ok="submitDoctor">
      <a-form layout="vertical">
        <a-form-item label="姓名" required>
          <a-input v-model:value="doctorModal.form.display_name" />
        </a-form-item>
        <a-form-item label="职称">
          <a-input v-model:value="doctorModal.form.title" />
        </a-form-item>
        <a-form-item label="擅长（逗号分隔）">
          <a-input v-model:value="doctorModal.specialtiesText" />
        </a-form-item>
        <a-form-item label="资质状态">
          <a-select v-model:value="doctorModal.form.license_status">
            <a-select-option value="unverified">待核验</a-select-option>
            <a-select-option value="verified">已核验</a-select-option>
            <a-select-option value="suspended">已暂停</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="展示状态">
          <a-select v-model:value="doctorModal.form.profile_status">
            <a-select-option value="draft">草稿</a-select-option>
            <a-select-option value="active">有效</a-select-option>
            <a-select-option value="hidden">隐藏</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="简介">
          <a-textarea v-model:value="doctorModal.form.introduction" :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>

    <ClinicalAgentFormModal
      v-model:open="agentForm.open"
      :hospital-id="hospitalId"
      :agent-id="agentForm.agentId"
      @saved="loadAgents"
    />
  </a-spin>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Modal, message } from 'ant-design-vue';
import {
  activateHospital,
  createDepartment,
  fetchAgents,
  fetchDepartments,
  fetchDoctors,
  fetchHospital,
  fetchHospitalAuditLogs,
  fetchStaff,
  hospitalCareMessage,
  inviteStaff,
  reviewAgent,
  suspendHospital,
  updateDepartment,
  updateDoctor,
  updateHospital,
  updateStaff,
  type AgentRow,
  type DepartmentRow,
  type DepartmentStatus,
  type DoctorRow,
  type HospitalAuditRow,
  type HospitalDraft,
  type HospitalOverview,
  type HospitalRow,
  type StaffRow,
} from '../../api/modules/hospitalCare';
import { fetchUsers } from '../../api/modules/users';
import type { Pagination } from '../../types';
import { useAuthStore } from '../../stores/auth';
import { formatDateTime } from '../../utils/datetime';
import { useDebouncedFn } from '../../utils/useDebouncedFn';
import HospitalBaseInfoForm from '../../components/hospital-care/HospitalBaseInfoForm.vue';
import ClinicalAgentFormModal from '../../components/hospital-care/ClinicalAgentFormModal.vue';
import HospitalKnowledgeTab from '../../components/hospital-care/HospitalKnowledgeTab.vue';
import TableHoverActions from '../../components/TableHoverActions.vue';
import {
  AGENT_STATUS_COLOR,
  AGENT_STATUS_LABEL,
  DEPARTMENT_STATUS_LABEL,
  DOCTOR_PROFILE_STATUS_LABEL,
  HOSPITAL_STATUS_COLOR,
  HOSPITAL_STATUS_LABEL,
  LICENSE_STATUS_LABEL,
  SERVICE_MODE_LABEL,
  STAFF_ROLE_LABEL,
  STAFF_STATUS_LABEL,
} from './hospitalCareLabels';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const loading = ref(false);
const statusSaving = ref(false);
const errorText = ref('');
const hospital = ref<HospitalRow | null>(null);
const activeTab = ref('overview');
const peopleTab = ref('staff');
const editingBase = ref(false);
const baseSaving = ref(false);
const baseForm = reactive<HospitalDraft>(emptyDraft());
const overview = reactive<HospitalOverview>({
  department_count: 0,
  doctor_count: 0,
  published_agent_count: 0,
  active_conversation_count: 0,
  pending_license_count: 0,
  pending_review_agent_count: 0,
});

const departments = ref<DepartmentRow[]>([]);
const deptLoading = ref(false);
const departmentQuery = reactive({ q: '', status: '' });

const staffRows = ref<StaffRow[]>([]);
const staffLoading = ref(false);
const staffQuery = reactive({ page: 1, page_size: 20, q: '' });
const staffPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const doctorRows = ref<DoctorRow[]>([]);
const doctorLoading = ref(false);
const doctorQuery = reactive({ page: 1, page_size: 20, q: '' });
const doctorPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const agentRows = ref<AgentRow[]>([]);
const agentLoading = ref(false);
const agentQuery = reactive({ page: 1, page_size: 20, q: '', status: '', department_id: undefined as string | undefined });
const agentPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });
const agentForm = reactive({ open: false, agentId: undefined as string | undefined });

const auditRows = ref<HospitalAuditRow[]>([]);
const recentAudit = ref<HospitalAuditRow[]>([]);
const auditLoading = ref(false);
const auditQuery = reactive({ page: 1, page_size: 20, action: '' });
const auditPagination = reactive<Pagination>({ page: 1, page_size: 20, total: 0, total_pages: 0 });

const userOptions = ref<Array<{ value: number; label: string }>>([]);

const deptModal = reactive({
  open: false,
  isCreate: true,
  saving: false,
  id: '',
  form: { code: '', name: '', short_name: '', parent_id: undefined as string | undefined, sort_order: 0, status: 'active' as DepartmentStatus, description: '' },
});

const inviteModal = reactive({
  open: false,
  saving: false,
  form: {
    user_id: undefined as number | undefined,
    role: 'hospital_admin' as StaffRow['role'],
    employee_no: '',
    status: 'active' as StaffRow['status'],
    display_name: '',
    title: '',
  },
});

const staffModal = reactive({
  open: false,
  saving: false,
  id: '',
  username: '',
  lockedRole: false,
  form: {
    role: 'hospital_admin' as StaffRow['role'],
    employee_no: '',
    status: 'active' as StaffRow['status'],
    display_name: '',
    title: '',
  },
});

const doctorModal = reactive({
  open: false,
  saving: false,
  id: '',
  specialtiesText: '',
  form: {
    display_name: '',
    title: '',
    introduction: '',
    license_status: 'unverified' as DoctorRow['license_status'],
    profile_status: 'draft' as DoctorRow['profile_status'],
  },
});

const reasonModal = reactive({
  open: false,
  saving: false,
  title: '',
  description: '',
  reason: '',
  kind: '' as '' | 'suspend' | 'reject' | 'disable',
  agent: null as AgentRow | null,
});

const canUpdate = computed(() => auth.hasPermission('button:hospital_care:hospital:update'));
const canActivate = computed(() => auth.hasPermission('button:hospital_care:hospital:activate'));
const canSuspend = computed(() => auth.hasPermission('button:hospital_care:hospital:suspend'));
const canUpdateDept = computed(() => auth.hasPermission('api:hospital_care:department:create') || auth.hasPermission('button:hospital_care:hospital:update'));
const canInvite = computed(() => auth.hasPermission('api:hospital_care:staff:create') || auth.hasPermission('button:hospital_care:hospital:update'));
const canUpdateStaff = computed(() => auth.hasPermission('api:hospital_care:staff:update') || auth.hasPermission('button:hospital_care:hospital:update'));
const canUpdateDoctor = computed(() => auth.hasPermission('api:hospital_care:doctor:update') || auth.hasPermission('button:hospital_care:hospital:update'));
const canReview = computed(() => auth.hasPermission('api:hospital_care:agent:review') || auth.hasPermission('button:hospital_care:hospital:update'));
const canCreateAgent = computed(() => auth.hasPermission('button:hospital_care:agent:create') || auth.hasPermission('api:hospital_care:agent:create'));
const canUpdateAgent = computed(() => auth.hasPermission('button:hospital_care:agent:update') || auth.hasPermission('api:hospital_care:agent:update'));
const canCreateKnowledge = computed(() => auth.hasPermission('button:hospital_care:knowledge:create') || auth.hasPermission('api:hospital_care:knowledge:create'));
const canUpdateKnowledge = computed(() => auth.hasPermission('button:hospital_care:knowledge:update') || auth.hasPermission('api:hospital_care:knowledge:update'));
const canDeleteKnowledge = computed(() => auth.hasPermission('button:hospital_care:knowledge:delete') || auth.hasPermission('api:hospital_care:knowledge:delete'));
const canBuildKnowledge = computed(() => auth.hasPermission('button:hospital_care:knowledge:vector_build') || auth.hasPermission('api:hospital_care:knowledge:vector_build'));
const pendingItems = computed(
  () => overview.pending_license_count || overview.pending_review_agent_count || hospital.value?.service_mode === 'demo',
);
const parentOptions = computed(() => departments.value.filter((item) => item.id !== deptModal.id));
const hospitalId = computed(() => String(route.params.hospitalId || '').trim());
const isStandalone = computed(() => route.path.startsWith('/hospital-system/'));
const displayedTab = computed(() => (isStandalone.value ? String(route.params.tab || 'overview') : activeTab.value));
const tabMeta: Record<string, { title: string; description: string }> = {
  overview: { title: '医院概览', description: '查看医院服务运行状态、待处理事项和最近管理操作。' },
  base: { title: '基础资料', description: '维护医院对外展示信息、服务模式和联系方式。' },
  departments: { title: '科室管理', description: '配置医院科室及其服务范围，为医生和智能体建立归属关系。' },
  people: { title: '职工与医生', description: '管理医院成员、医生资质和患者端展示信息。' },
  agents: { title: '智能体管理', description: '审核并管理院内医生智能体、知识库绑定和发布状态。' },
  knowledge: { title: '医院知识库', description: '录入院内文本资料、手工生成向量，并供智能体绑定复用。' },
  integration: { title: '服务接入', description: '查看挂号、就医服务和医院系统的接入状态。' },
  audit: { title: '审计记录', description: '追踪医院范围内的关键配置变更和操作结果。' },
};
const currentTabTitle = computed(() => tabMeta[displayedTab.value]?.title || '医院系统');
const currentTabDescription = computed(() => tabMeta[displayedTab.value]?.description || '管理当前医院的服务配置。');

function hasHospitalId() {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(hospitalId.value);
}

function emptyDraft(): HospitalDraft {
  return {
    code: '',
    name: '',
    short_name: '',
    grade: '',
    province_code: '',
    city_code: '',
    district_code: '',
    address: '',
    service_phone: '',
    emergency_phone: '',
    website_url: '',
    introduction: '',
    registration_redirect_url: '',
    service_mode: 'demo',
  };
}

function regionText(row: HospitalRow) {
  return [row.province_code, row.city_code, row.district_code].filter(Boolean).join(' / ') || '--';
}

function licenseLabel(value: string) {
  return LICENSE_STATUS_LABEL[value as keyof typeof LICENSE_STATUS_LABEL] || value;
}

function departmentStatusLabel(value: string) {
  return DEPARTMENT_STATUS_LABEL[value as keyof typeof DEPARTMENT_STATUS_LABEL] || value;
}

function staffRoleLabel(value: string) {
  return STAFF_ROLE_LABEL[value as keyof typeof STAFF_ROLE_LABEL] || value;
}

function staffStatusLabel(value: string) {
  return STAFF_STATUS_LABEL[value as keyof typeof STAFF_STATUS_LABEL] || value;
}

function doctorProfileStatusLabel(value: string) {
  return DOCTOR_PROFILE_STATUS_LABEL[value as keyof typeof DOCTOR_PROFILE_STATUS_LABEL] || value;
}

function agentStatusLabel(value: string) {
  return AGENT_STATUS_LABEL[value as keyof typeof AGENT_STATUS_LABEL] || value;
}

function agentStatusColor(value: string) {
  return AGENT_STATUS_COLOR[value as keyof typeof AGENT_STATUS_COLOR] || 'default';
}

function applyHospital(row: HospitalRow) {
  hospital.value = row;
  Object.assign(baseForm, {
    code: row.code,
    name: row.name,
    short_name: row.short_name,
    grade: row.grade,
    province_code: row.province_code,
    city_code: row.city_code,
    district_code: row.district_code,
    address: row.address,
    service_phone: row.service_phone,
    emergency_phone: row.emergency_phone,
    website_url: row.website_url,
    introduction: row.introduction,
    registration_redirect_url: row.registration_redirect_url,
    service_mode: row.service_mode,
  });
  if (row.overview) {
    Object.assign(overview, row.overview);
  }
}

async function loadHospital() {
  if (!hasHospitalId()) {
    return;
  }
  loading.value = true;
  try {
    applyHospital(await fetchHospital(hospitalId.value));
    errorText.value = '';
  } catch (error) {
    errorText.value = hospitalCareMessage(error);
  } finally {
    loading.value = false;
  }
}

function parentName(parentId: string | null) {
  if (!parentId) {
    return '--';
  }
  return departments.value.find((item) => item.id === parentId)?.name || '--';
}

async function loadDepartments() {
  if (!hasHospitalId()) {
    return;
  }
  deptLoading.value = true;
  try {
    const data = await fetchDepartments(hospitalId.value, departmentQuery);
    departments.value = data.items;
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    deptLoading.value = false;
  }
}

async function loadStaff() {
  if (!hasHospitalId()) {
    return;
  }
  staffLoading.value = true;
  try {
    const data = await fetchStaff(hospitalId.value, staffQuery);
    staffRows.value = data.items;
    Object.assign(staffPagination, data.pagination);
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    staffLoading.value = false;
  }
}

async function loadDoctors() {
  if (!hasHospitalId()) {
    return;
  }
  doctorLoading.value = true;
  try {
    const data = await fetchDoctors(hospitalId.value, doctorQuery);
    doctorRows.value = data.items;
    Object.assign(doctorPagination, data.pagination);
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    doctorLoading.value = false;
  }
}

async function loadAgents() {
  if (!hasHospitalId()) {
    return;
  }
  agentLoading.value = true;
  try {
    const data = await fetchAgents(hospitalId.value, agentQuery);
    agentRows.value = data.items;
    Object.assign(agentPagination, data.pagination);
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    agentLoading.value = false;
  }
}

async function loadAudit() {
  if (!hasHospitalId()) {
    return;
  }
  auditLoading.value = true;
  try {
    const data = await fetchHospitalAuditLogs(hospitalId.value, auditQuery);
    auditRows.value = data.items;
    Object.assign(auditPagination, data.pagination);
    if (!auditQuery.action && auditQuery.page === 1) {
      recentAudit.value = data.items.slice(0, 5);
    }
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    auditLoading.value = false;
  }
}

function onTabChange(key: string | number) {
  if (isStandalone.value) {
    router.push({ name: 'HospitalSystemSection', params: { hospitalId: hospitalId.value, tab: String(key) } });
    return;
  }
  activeTab.value = String(key);
  loadTabData(String(key));
}

function loadTabData(key: string) {
  if (key === 'departments' || key === 'agents' || key === 'knowledge') {
    loadDepartments();
  }
  if (key === 'people') {
    loadStaff();
    loadDoctors();
  }
  if (key === 'agents') {
    loadAgents();
  }
  if (key === 'audit') {
    loadAudit();
  }
}

function openAgentForm(row?: AgentRow) {
  agentForm.agentId = row?.id;
  agentForm.open = true;
}

function cancelEditBase() {
  if (hospital.value) {
    applyHospital(hospital.value);
  }
  editingBase.value = false;
}

async function saveBase() {
  if (!hospital.value) {
    return;
  }
  baseSaving.value = true;
  try {
    const updated = await updateHospital(hospital.value.id, { ...baseForm, version: hospital.value.version });
    applyHospital(updated);
    editingBase.value = false;
    message.success('已保存医院资料');
  } catch (error) {
    message.error(hospitalCareMessage(error));
    if (error instanceof Error && error.message.includes('HOSPITAL_VERSION_CONFLICT')) {
      await loadHospital();
    }
  } finally {
    baseSaving.value = false;
  }
}

function onActivate() {
  if (!hospital.value) {
    return;
  }
  Modal.confirm({
    title: `启用${hospital.value.name}？`,
    content: '启用后患者端可发现该医院，并可按当前服务模式使用入口。启用前需具备完整基础资料和有效医院管理员。',
    onOk: async () => {
      statusSaving.value = true;
      try {
        applyHospital(await activateHospital(hospital.value!.id, hospital.value!.version));
        message.success('医院已启用');
      } catch (error) {
        message.error(hospitalCareMessage(error));
        throw error;
      } finally {
        statusSaving.value = false;
      }
    },
  });
}

function openSuspend() {
  if (!hospital.value) {
    return;
  }
  reasonModal.kind = 'suspend';
  reasonModal.title = '暂停医院服务';
  reasonModal.description = '暂停后禁止创建新的挂号和医院咨询；历史会话仍可查看。';
  reasonModal.reason = '';
  reasonModal.agent = null;
  reasonModal.open = true;
}

function openDepartment(row?: DepartmentRow) {
  deptModal.isCreate = !row;
  deptModal.id = row?.id || '';
  deptModal.form = {
    code: row?.code || '',
    name: row?.name || '',
    short_name: row?.short_name || '',
    parent_id: row?.parent_id || undefined,
    sort_order: row?.sort_order || 0,
    status: row?.status || 'active',
    description: row?.description || '',
  };
  deptModal.open = true;
}

async function submitDepartment() {
  deptModal.saving = true;
  try {
    if (deptModal.isCreate) {
      await createDepartment(hospitalId.value, deptModal.form);
      message.success('已新增科室');
    } else {
      await updateDepartment(deptModal.id, deptModal.form);
      message.success('已更新科室');
    }
    deptModal.open = false;
    await loadDepartments();
    await loadHospital();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    deptModal.saving = false;
  }
}

function openInvite() {
  inviteModal.form = {
    user_id: undefined,
    role: 'hospital_admin',
    employee_no: '',
    status: 'active',
    display_name: '',
    title: '',
  };
  inviteModal.open = true;
  onUserSearch('');
}

const onUserSearch = useDebouncedFn(async (keyword: string) => {
  const data = await fetchUsers({ page: 1, page_size: 20, q: keyword });
  userOptions.value = data.items.map((item) => ({
    value: item.id,
    label: `${item.display_name || item.username}（${item.username}）`,
  }));
}, 300);

async function submitInvite() {
  if (!inviteModal.form.user_id) {
    message.error('请选择用户账号');
    return;
  }
  inviteModal.saving = true;
  try {
    await inviteStaff(hospitalId.value, {
      user_id: inviteModal.form.user_id,
      role: inviteModal.form.role,
      employee_no: inviteModal.form.employee_no,
      status: inviteModal.form.status,
      display_name: inviteModal.form.display_name,
      title: inviteModal.form.title,
    });
    message.success('已邀请职工');
    inviteModal.open = false;
    await loadStaff();
    if (inviteModal.form.role === 'doctor') {
      await loadDoctors();
    }
    await loadHospital();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    inviteModal.saving = false;
  }
}

function openStaff(row: StaffRow) {
  staffModal.id = row.id;
  staffModal.username = row.username;
  staffModal.lockedRole = row.role === 'doctor';
  staffModal.form = {
    role: row.role,
    employee_no: row.employee_no || '',
    status: row.status,
    display_name: '',
    title: '',
  };
  staffModal.open = true;
}

async function submitStaff() {
  staffModal.saving = true;
  try {
    await updateStaff(staffModal.id, {
      role: staffModal.form.role,
      employee_no: staffModal.form.employee_no,
      status: staffModal.form.status,
      display_name: staffModal.form.display_name,
      title: staffModal.form.title,
    });
    message.success('已更新职工');
    staffModal.open = false;
    await loadStaff();
    if (staffModal.form.role === 'doctor') {
      await loadDoctors();
    }
    await loadHospital();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    staffModal.saving = false;
  }
}

function openDoctor(row: DoctorRow) {
  doctorModal.id = row.id;
  doctorModal.specialtiesText = (row.specialties || []).join('，');
  doctorModal.form = {
    display_name: row.display_name,
    title: row.title,
    introduction: row.introduction,
    license_status: row.license_status,
    profile_status: row.profile_status,
  };
  doctorModal.open = true;
}

async function submitDoctor() {
  doctorModal.saving = true;
  try {
    await updateDoctor(doctorModal.id, {
      ...doctorModal.form,
      specialties: doctorModal.specialtiesText
        .split(/[,，]/)
        .map((item) => item.trim())
        .filter(Boolean),
    });
    message.success('已更新医生资料');
    doctorModal.open = false;
    await loadDoctors();
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    doctorModal.saving = false;
  }
}

function openReview(row: AgentRow, action: 'publish' | 'reject' | 'disable') {
  if (action === 'publish') {
    Modal.confirm({
      title: '通过并发布智能体',
      content: '通过后患者端可发现该智能体。审核页不展示 Provider Key。',
      onOk: async () => {
        try {
          await reviewAgent(row.id, { action: 'publish', version: row.version || 1 });
          message.success('已更新智能体状态');
          await loadAgents();
          await loadHospital();
        } catch (error) {
          message.error(hospitalCareMessage(error));
          throw error;
        }
      },
    });
    return;
  }
  reasonModal.kind = action;
  reasonModal.title = action === 'reject' ? '驳回智能体' : '暂停智能体';
  reasonModal.description = action === 'reject' ? '驳回必须填写原因。' : '暂停智能体不会删除历史会话。';
  reasonModal.reason = '';
  reasonModal.agent = row;
  reasonModal.open = true;
}

async function submitReason() {
  const reason = reasonModal.reason.trim();
  if (!reason) {
    message.error('原因必填');
    return;
  }
  reasonModal.saving = true;
  try {
    if (reasonModal.kind === 'suspend' && hospital.value) {
      applyHospital(await suspendHospital(hospital.value.id, hospital.value.version, reason));
      message.success('医院已暂停');
    } else if ((reasonModal.kind === 'reject' || reasonModal.kind === 'disable') && reasonModal.agent) {
      await reviewAgent(reasonModal.agent.id, {
        action: reasonModal.kind,
        version: reasonModal.agent.version || 1,
        reason,
      });
      message.success('已更新智能体状态');
      await loadAgents();
      await loadHospital();
    }
    reasonModal.open = false;
  } catch (error) {
    message.error(hospitalCareMessage(error));
  } finally {
    reasonModal.saving = false;
  }
}

function onStaffPage(page: number, pageSize: number) {
  staffQuery.page = page;
  staffQuery.page_size = pageSize;
  loadStaff();
}

function onDoctorPage(page: number, pageSize: number) {
  doctorQuery.page = page;
  doctorQuery.page_size = pageSize;
  loadDoctors();
}

function onAgentPage(page: number, pageSize: number) {
  agentQuery.page = page;
  agentQuery.page_size = pageSize;
  loadAgents();
}

function onAuditPage(page: number, pageSize: number) {
  auditQuery.page = page;
  auditQuery.page_size = pageSize;
  loadAudit();
}

watch(hospitalId, async () => {
  if (!hasHospitalId()) {
    return;
  }
  await loadHospital();
  await loadAudit();
});

watch(
  () => route.params.tab,
  (tab) => {
    if (isStandalone.value && tab) {
      activeTab.value = String(tab);
      loadTabData(String(tab));
    }
  },
  { immediate: true },
);

onMounted(async () => {
  if (!hasHospitalId()) {
    return;
  }
  await loadHospital();
  await loadAudit();
});
</script>

<style scoped>
.standalone-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}

.standalone-section-heading h2 {
  margin: 0;
  color: #182230;
  font-size: 22px;
  line-height: 1.35;
  font-weight: 650;
}

.standalone-section-heading p {
  margin: 6px 0 0;
  color: #7f8a9a;
  font-size: 13px;
  line-height: 1.5;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.overview-metric {
  min-height: 116px;
  padding: 18px 20px;
  box-sizing: border-box;
  border: 1px solid #edf0f4;
  border-radius: 8px;
  background: #fff;
}

.overview-metric:not(.overview-metric-accent) {
  background: #fbfcfe;
}

.overview-metric span,
.overview-metric small {
  display: block;
  color: #7f8a9a;
}

.overview-metric span {
  font-size: 14px;
}

.overview-metric strong {
  display: block;
  margin: 8px 0 4px;
  color: #182230;
  font-size: 30px;
  line-height: 1;
  font-weight: 650;
}

.overview-metric small {
  font-size: 12px;
}

.overview-metric-accent {
  border-color: #cfe3ff;
  background: #f7fbff;
}

.overview-metric-accent strong {
  color: #1677ff;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(0, 1.8fr);
  gap: 16px;
  align-items: start;
}

.overview-card {
  height: 100%;
}

.pending-list {
  min-height: 72px;
  margin: 0;
  padding: 0 0 0 18px;
  color: #445064;
  line-height: 2;
}

.overview-card :deep(.ant-card-head) {
  min-height: 48px;
  padding: 0 18px;
  border-bottom-color: #edf0f4;
}

.overview-card :deep(.ant-card-head-title) {
  color: #263244;
  font-weight: 600;
}

.overview-audit-card :deep(.ant-card-body) {
  padding: 0 12px 12px;
}

@media (max-width: 900px) {
  .overview-metrics,
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .overview-metrics,
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
