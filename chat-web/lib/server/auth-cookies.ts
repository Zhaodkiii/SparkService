interface CookieOptions { httpOnly?: boolean; secure?: boolean; sameSite?: "lax" | "strict" | "none"; path?: string; maxAge?: number; expires?: Date; }

export const REFRESH_COOKIE = process.env.NODE_ENV === "production" ? "__Host-spark_refresh" : "spark_refresh_dev";
export const APPLE_STATE_COOKIE = process.env.NODE_ENV === "production" ? "__Host-spark_apple_state" : "spark_apple_state_dev";
export const APPLE_NONCE_COOKIE = process.env.NODE_ENV === "production" ? "__Host-spark_apple_nonce" : "spark_apple_nonce_dev";
export const APPLE_RETURN_COOKIE = process.env.NODE_ENV === "production" ? "__Host-spark_apple_return" : "spark_apple_return_dev";

export function refreshCookieOptions(): CookieOptions {
  return { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30 };
}

export function transientCookieOptions(): CookieOptions {
  const production = process.env.NODE_ENV === "production";
  return { httpOnly: true, secure: production, sameSite: production ? "none" : "lax", path: "/", maxAge: 10 * 60 };
}

export function clearCookieOptions(): CookieOptions {
  return { ...refreshCookieOptions(), maxAge: 0, expires: new Date(0) };
}
