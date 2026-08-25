import { ChatRuntimeProvider } from "@/context/ChatRuntimeContext";
import { ThreadProvider } from "@/context/ThreadContext";
import { RunControlProvider } from "@/context/RunControlContext";
import { ChatContextProvider } from "@/context/ChatContextProvider";
import { AuthGate } from "@/components/auth/AuthGate";
import { ResponsiveAppShell } from "@/components/layout/ResponsiveAppShell";

export default function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AuthGate><ChatRuntimeProvider><ThreadProvider><ChatContextProvider><RunControlProvider><ResponsiveAppShell>{children}</ResponsiveAppShell></RunControlProvider></ChatContextProvider></ThreadProvider></ChatRuntimeProvider></AuthGate>;
}
