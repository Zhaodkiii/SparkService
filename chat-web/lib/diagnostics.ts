export type ClientLogLevel = "info" | "warn" | "error";

type SafeFields = Record<string, string | number | boolean | null | undefined>;

function clientLogsEnabled(): boolean {
  return process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_SPARK_CLIENT_LOGS === "true";
}

export function sparkClientLog(level: ClientLogLevel, event: string, fields: SafeFields = {}): void {
  if (!clientLogsEnabled() && level === "info") return;
  const payload = {
    timestamp: new Date().toISOString(),
    source: "spark-chat-web",
    level,
    event,
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined)),
  };
  const line = `[SparkChat] ${JSON.stringify(payload)}`;
  if (level === "error") console.warn(line);
  else if (level === "warn") console.warn(line);
  else console.info(line);
}

export function clientErrorDetails(cause: unknown): { error_type: string; error_message?: string } {
  return {
    error_type: cause instanceof Error ? cause.name : typeof cause,
    error_message: cause instanceof Error ? cause.message.slice(0, 240) : undefined,
  };
}
