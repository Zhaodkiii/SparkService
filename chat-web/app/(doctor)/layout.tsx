import { AuthGate } from "@/components/auth/AuthGate";
import { DoctorRealtimeBridge } from "@/components/doctor/DoctorRealtimeBridge";
import { DoctorAppShell } from "@/components/layout/DoctorAppShell";
import { DoctorAuthGate } from "@/context/DoctorAuthGate";
import { DoctorConversationsProvider } from "@/context/DoctorConversationsContext";
import { PatientWorkspaceProvider } from "@/context/PatientWorkspaceContext";

export default function DoctorLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <AuthGate>
      <DoctorAuthGate>
        <DoctorConversationsProvider>
          <PatientWorkspaceProvider>
            <DoctorRealtimeBridge />
            <DoctorAppShell>{children}</DoctorAppShell>
          </PatientWorkspaceProvider>
        </DoctorConversationsProvider>
      </DoctorAuthGate>
    </AuthGate>
  );
}
