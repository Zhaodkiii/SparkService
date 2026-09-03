"use client";

import { PatientAsidePanel } from "@/components/doctor/PatientAsidePanel";
import { PatientListPanel } from "@/components/doctor/PatientListPanel";
import { PatientWorkspaceMain } from "@/components/doctor/PatientWorkspaceMain";
import { CurrentAgentHeader } from "@/components/doctor/CurrentAgentHeader";

/** D-028：患者信息优先的纵向布局——左侧患者列表，中间患者工作台，右侧会话抽屉/辅助信息。 */
export function PatientWorkspacePage() {
  return (
    <div className="patient-workspace">
      <CurrentAgentHeader />
      <PatientListPanel />
      <PatientWorkspaceMain />
      <PatientAsidePanel />
    </div>
  );
}
