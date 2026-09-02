"use client";
/* eslint-disable react-hooks/refs, react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { SparkAuthApi } from "@/lib/api/auth-api";
import { SparkHttpClient } from "@/lib/api/http-client";
import { authDiagnosticLog, createAuthRequestId } from "@/lib/auth/diagnostics";
import type { AuthTokenWireDTO, CurrentSessionDTO } from "@/types/auth";

type AuthStatus = "bootstrapping" | "anonymous" | "authenticated" | "refreshing";
interface AuthValue {
  status: AuthStatus;
  accessToken: string | null;
  session: CurrentSessionDTO | null;
  client: SparkHttpClient;
  login: (token: AuthTokenWireDTO) => Promise<void>;
  refresh: () => Promise<string | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const tokenRef = useRef<string | null>(null);
  const refreshInFlight = useRef<Promise<string | null> | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [session, setSession] = useState<CurrentSessionDTO | null>(null);
  const [status, setStatus] = useState<AuthStatus>("bootstrapping");

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const requestId = createAuthRequestId("refresh");
    const startedAt = Date.now();
    authDiagnosticLog("info", "browser", "auth.bootstrap.started", { request_id: requestId, session_class: "web" });
    setStatus((current) => current === "authenticated" ? "refreshing" : "bootstrapping");
    const pending = (async () => {
      try {
        const bootstrapClient = new SparkHttpClient({ baseUrl: "" });
        const data = await new SparkAuthApi(bootstrapClient).bootstrap(requestId);
        if (!data.access_token) throw new Error("missing access token");
        tokenRef.current = data.access_token;
        setAccessToken(data.access_token);
        setSession(data.session ?? null);
        setStatus("authenticated");
        authDiagnosticLog("info", "browser", "auth.bootstrap.succeeded", { request_id: requestId, duration_ms: Date.now() - startedAt });
        return data.access_token;
      } catch (cause) {
        authDiagnosticLog("warn", "browser", "auth.bootstrap.failed", { request_id: requestId, duration_ms: Date.now() - startedAt, error_type: cause instanceof Error ? cause.name : typeof cause });
        tokenRef.current = null;
        setAccessToken(null);
        setSession(null);
        setStatus("anonymous");
        return null;
      } finally {
        refreshInFlight.current = null;
      }
    })();
    refreshInFlight.current = pending;
    return pending;
  }, []);

  const login = useCallback(async (token: AuthTokenWireDTO) => {
    tokenRef.current = token.access_token;
    setAccessToken(token.access_token);
    try {
      const api = new SparkAuthApi(new SparkHttpClient({ baseUrl: "", getAccessToken: () => token.access_token }));
      setSession(await api.currentSession());
    } catch { setSession(null); }
    setStatus("authenticated");
  }, []);

  const client = useMemo(() => new SparkHttpClient({ baseUrl: "", getAccessToken: () => tokenRef.current, refreshAccessToken: refresh }), [refresh]);

  const logout = useCallback(async () => {
    try { await new SparkAuthApi(client).logout(); } catch { /* local logout must still complete */ }
    tokenRef.current = null;
    setAccessToken(null);
    setSession(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  const value = useMemo(() => ({ status, accessToken, session, client, login, refresh, logout }), [status, accessToken, session, client, login, refresh, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function useOptionalAuth() { return useContext(AuthContext); }
