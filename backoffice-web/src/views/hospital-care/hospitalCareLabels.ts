import type {
  AgentPublicationStatus,
  DepartmentStatus,
  DoctorProfileStatus,
  HospitalServiceMode,
  HospitalStatus,
  KnowledgeVectorStatus,
  LicenseStatus,
  StaffRole,
  StaffStatus,
} from '../../api/modules/hospitalCare';

export const HOSPITAL_STATUS_LABEL: Record<HospitalStatus, string> = {
  draft: '草稿',
  active: '已启用',
  suspended: '已暂停',
};

export const HOSPITAL_STATUS_COLOR: Record<HospitalStatus, string> = {
  draft: 'default',
  active: 'green',
  suspended: 'orange',
};

export const SERVICE_MODE_LABEL: Record<HospitalServiceMode, string> = {
  demo: 'Demo 演示',
  redirect: '跳转官方入口',
  integrated: 'HIS 已接入',
};

export const DEPARTMENT_STATUS_LABEL: Record<DepartmentStatus, string> = {
  active: '启用',
  hidden: '隐藏',
};

export const STAFF_ROLE_LABEL: Record<StaffRole, string> = {
  hospital_admin: '医院管理员',
  doctor: '医生',
  nurse: '护士',
  auditor: '审计员',
};

export const STAFF_STATUS_LABEL: Record<StaffStatus, string> = {
  invited: '已邀请',
  active: '有效',
  suspended: '已停用',
};

export const LICENSE_STATUS_LABEL: Record<LicenseStatus, string> = {
  unverified: '待核验',
  verified: '已核验',
  suspended: '已暂停',
};

export const DOCTOR_PROFILE_STATUS_LABEL: Record<DoctorProfileStatus, string> = {
  draft: '草稿',
  active: '有效',
  hidden: '隐藏',
};

export const AGENT_STATUS_LABEL: Record<AgentPublicationStatus, string> = {
  draft: '草稿',
  review: '待审核',
  published: '已发布',
  disabled: '已暂停',
};

export const AGENT_STATUS_COLOR: Record<AgentPublicationStatus, string> = {
  draft: 'default',
  review: 'gold',
  published: 'green',
  disabled: 'orange',
};

export const VECTOR_STATUS_LABEL: Record<KnowledgeVectorStatus, string> = {
  not_built: '待生成',
  current: '已生成（当前）',
  stale: '已过期',
};

export const VECTOR_STATUS_COLOR: Record<KnowledgeVectorStatus, string> = {
  not_built: 'default',
  current: 'green',
  stale: 'orange',
};

export const GRADE_OPTIONS = ['三甲', '三乙', '三级', '二甲', '二乙', '二级', '一级'].map((value) => ({
  value,
  label: value,
}));
