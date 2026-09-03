import { PatientWorkspacePage } from "@/components/doctor/PatientWorkspacePage";

/** DOCTOR-WORKSPACE-000001：患者工作台。
 *  可选 slug 形态：
 *  - /doctor/patients                                   列表（自动选中第一位患者）
 *  - /doctor/patients/<memberId>                        患者工作台（抽屉关闭）
 *  - /doctor/patients/<memberId>/conversations/<threadId>  右侧会话抽屉打开
 *  路由解析由 PatientWorkspaceContext / DoctorConversationsContext 按 pathname 完成。 */
export default function DoctorPatientsPage() {
  return <PatientWorkspacePage />;
}
