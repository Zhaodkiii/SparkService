"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth(); const router = useRouter();
  useEffect(() => { if (auth.status === "anonymous") router.replace("/login" as never); }, [auth.status, router]);
  if (auth.status === "bootstrapping" || auth.status === "refreshing") return <main className="workspace workspace--loading" aria-busy="true"><p>正在恢复登录状态…</p></main>;
  if (auth.status !== "authenticated") return null;
  return <>{children}</>;
}
