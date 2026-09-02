import { AuthGate } from "@/components/auth/AuthGate";
import { DoctorAppShell } from "@/components/layout/DoctorAppShell";
import { DoctorAuthGate } from "@/context/DoctorAuthGate";
import { DoctorConversationsProvider } from "@/context/DoctorConversationsContext";

export default function DoctorLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <AuthGate>
      <DoctorAuthGate>
        <DoctorConversationsProvider>
          <DoctorAppShell>{children}</DoctorAppShell>
        </DoctorConversationsProvider>
      </DoctorAuthGate>
    </AuthGate>
  );
}
