export type AuthLogLevel = "info" | "warn" | "error";
export type AuthLogSource = "browser" | "bff";

type AuthLogFields = Record<string, string | number | boolean | null | undefined>;

export function createAuthRequestId(operation: "request" | "verify" | "refresh"): string {
  const suffix = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `phone-otp-${operation}-${suffix}`;
}

export function maskPhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length < 7) return "***";
  return `${digits.slice(0, 2)}***${digits.slice(-4)}`;
}

import { sparkDiagnosticLogsEnabled } from "@/lib/diagnostics";

export function authDiagnosticLog(
  level: AuthLogLevel,
  source: AuthLogSource,
  event: string,
  fields: AuthLogFields = {},
): void {
  // Server-side Apple troubleshooting can be enabled without enabling all browser logs.
  if (!sparkDiagnosticLogsEnabled() && process.env.SPARK_AUTH_DIAGNOSTIC_LOGS !== "1" && process.env.SPARK_AUTH_DIAGNOSTIC_LOGS !== "true") return;
  const payload = {
    timestamp: new Date().toISOString(),
    source,
    level,
    event,
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined)),
  };
  const line = `[SparkAuth] ${JSON.stringify(payload)}`;
  // Next.js dev mode turns browser console.error into a blocking error overlay.
  // Operational API failures remain semantic `error` events, but use warn in the browser.
  if (level === "error" && source === "bff") console.error(line);
  else if (level === "error") console.warn(line);
  else if (level === "warn") console.warn(line);
  else console.info(line);
}
