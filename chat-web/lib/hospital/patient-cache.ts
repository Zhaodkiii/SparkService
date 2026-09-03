/** DOCTOR-WORKSPACE-000001 D-030/D-031：患者工作台模块级缓存。
 *
 *  命名空间：hospital_id + doctor_id + member_id + module_name。
 *  命中（含过期）先展示并后台刷新；过期仅作刷新前临时展示，不代表权限授权。
 *  切换医院/医生身份、退出登录或账号失效时清理对应范围缓存。
 */

export type PatientCacheModule = "profile" | "conversations" | "summary" | "risk";

export interface PatientCacheScope {
  hospitalId: string;
  doctorId: string;
  memberId: number;
  module: PatientCacheModule;
}

export interface PatientCacheEntry<T> {
  /** 缓存写入时间（ISO），用于页面标记“缓存于”。 */
  savedAt: string;
  /** 超过模块 TTL：仅允许作为刷新前的临时展示。 */
  stale: boolean;
  data: T;
}

const PREFIX = "doctor-patient-ws:v1";
const IDENTITY_KEY = `${PREFIX}:identity`;

export const PATIENT_CACHE_TTL_MS: Record<PatientCacheModule, number> = {
  profile: 5 * 60_000,
  conversations: 2 * 60_000,
  summary: 24 * 60 * 60_000,
  risk: 5 * 60_000,
};

function storageKey(scope: PatientCacheScope): string {
  return `${PREFIX}:${scope.hospitalId}:${scope.doctorId}:${scope.memberId}:${scope.module}`;
}

interface WireFormat<T> {
  savedAt: string;
  data: T;
}

export function readPatientCache<T>(scope: PatientCacheScope): PatientCacheEntry<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as WireFormat<T>;
    if (!parsed || typeof parsed.savedAt !== "string") return null;
    const savedAtMs = Date.parse(parsed.savedAt);
    if (!Number.isFinite(savedAtMs)) return null;
    return {
      savedAt: parsed.savedAt,
      stale: Date.now() - savedAtMs > PATIENT_CACHE_TTL_MS[scope.module],
      data: parsed.data,
    };
  } catch {
    return null;
  }
}

export function writePatientCache<T>(scope: PatientCacheScope, data: T): void {
  if (typeof window === "undefined") return;
  try {
    const payload: WireFormat<T> = { savedAt: new Date().toISOString(), data };
    window.localStorage.setItem(storageKey(scope), JSON.stringify(payload));
  } catch {
    /* 配额或隐私模式下忽略写入失败 */
  }
}

function removeKeysWithPrefix(prefix: string): void {
  if (typeof window === "undefined") return;
  try {
    const keys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key && key !== IDENTITY_KEY && key.startsWith(prefix)) keys.push(key);
    }
    for (const key of keys) window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

/** 按前缀清理：不传条件则清空全部患者工作台缓存。 */
export function clearPatientCache(partial: { hospitalId?: string; doctorId?: string; memberId?: number } = {}): void {
  const segments = [PREFIX];
  if (partial.hospitalId) segments.push(partial.hospitalId);
  if (partial.doctorId) segments.push(partial.doctorId);
  if (partial.memberId !== undefined) segments.push(String(partial.memberId));
  removeKeysWithPrefix(segments.join(":"));
}

/** D-030：切换医院或医生身份时清理旧身份范围缓存。 */
export function ensurePatientCacheIdentity(hospitalId: string, doctorId: string): void {
  if (typeof window === "undefined") return;
  const current = `${hospitalId}:${doctorId}`;
  try {
    const previous = window.localStorage.getItem(IDENTITY_KEY);
    if (previous && previous !== current) removeKeysWithPrefix(PREFIX);
    window.localStorage.setItem(IDENTITY_KEY, current);
  } catch {
    /* ignore */
  }
}

/** D-030/D-031：退出登录、账号失效或服务关系撤回时清理全部敏感缓存。 */
export function clearAllPatientCache(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(IDENTITY_KEY);
  } catch {
    /* ignore */
  }
  removeKeysWithPrefix(PREFIX);
}
