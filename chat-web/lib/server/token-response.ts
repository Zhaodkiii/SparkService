export type RefreshTokenData = Record<string, unknown> & {
  access_token: string;
  refresh_token?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/** Accept Spark's current flat refresh response and the canonical API envelope. */
export function refreshTokenDataFromUpstream(body: unknown): RefreshTokenData | null {
  if (!isRecord(body)) return null;
  const candidate = isRecord(body.data) ? body.data : body;
  if (typeof candidate.access_token !== "string" || !candidate.access_token.trim()) return null;
  return candidate as RefreshTokenData;
}
