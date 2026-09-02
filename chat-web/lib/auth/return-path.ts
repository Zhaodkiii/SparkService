const FALLBACK = "/chat";

export function safeReturnPath(value: string | null | undefined, fallback = FALLBACK) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/login")) return fallback;
  return value;
}

export function loginUrl(returnTo?: string | null) {
  const next = safeReturnPath(returnTo);
  return next === FALLBACK ? "/login" : `/login?return_to=${encodeURIComponent(next)}`;
}
