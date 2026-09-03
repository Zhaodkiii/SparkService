import { redirect } from "next/navigation";

export default function DoctorIndexPage() {
  // DOCTOR-WORKSPACE-000001 D-001：工作台以患者为第一层级。
  redirect("/doctor/patients" as never);
}
