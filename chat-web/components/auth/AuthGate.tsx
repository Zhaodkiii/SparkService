"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { loginUrl } from "@/lib/auth/return-path";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (auth.status === "anonymous") router.replace(loginUrl(pathname) as never);
  }, [auth.status, pathname, router]);
  if (auth.status === "bootstrapping") return <main className="workspace workspace--loading" aria-busy="true"><p>正在恢复登录状态…</p></main>;
  if (auth.status !== "authenticated" && auth.status !== "refreshing") return null;
  return <>{children}</>;
}
