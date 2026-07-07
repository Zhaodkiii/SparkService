const SESSION_KEY = 'open_web_session_id';

export function useSessionId(): string {
  if (typeof window === 'undefined') {
    return `web_${Date.now()}_ssr`;
  }

  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) {
    return existing;
  }

  const random = Math.random().toString(36).slice(2, 10);
  const id = `web_${Date.now()}_${random}`;
  sessionStorage.setItem(SESSION_KEY, id);
  return id;
}
