// Persist only task identities. File bytes, credentials and signed URLs stay out of storage.
export interface RecoverableUpload {
  uploadID: string;
  libraryID: string;
  purpose: string;
  name: string;
  createdAt: number;
  attachedResource?: string;
  attachedRevision?: number;
}
const key = (account: string) => `material-upload-tasks:${account}`;
export function readUploads(account: string): RecoverableUpload[] {
  if (!account) return [];
  try {
    const rows = JSON.parse(localStorage.getItem(key(account)) || '[]');
    return Array.isArray(rows) ? rows.filter((r: RecoverableUpload) =>
      typeof r.uploadID === 'string' && typeof r.libraryID === 'string' &&
      Date.now() - r.createdAt < 7 * 86400000) : [];
  } catch { return []; }
}
export function rememberUpload(account: string, task: RecoverableUpload) {
  if (!account || !task.uploadID) return;
  const rows = readUploads(account).filter(r => r.uploadID !== task.uploadID);
  rows.push({uploadID: task.uploadID, libraryID: task.libraryID, purpose: task.purpose,
    name: task.name, createdAt: task.createdAt || Date.now(),
    attachedResource: task.attachedResource, attachedRevision: task.attachedRevision});
  try { localStorage.setItem(key(account), JSON.stringify(rows)); } catch { /* Page queue remains usable. */ }
}
export function forgetUpload(account: string, uploadID: string) {
  if (!account) return;
  try { localStorage.setItem(key(account), JSON.stringify(readUploads(account).filter(r => r.uploadID !== uploadID))); } catch { /* Storage may be unavailable. */ }
}
export function createUploadLimiter(limit: number) {
  let active = 0;
  const waiting: (() => void)[] = [];
  return async function<T>(work: () => Promise<T>): Promise<T> {
    await new Promise<void>(resolve => {
      const enter = () => { active++; resolve(); };
      if (active < limit) enter(); else waiting.push(enter);
    });
    try { return await work(); }
    finally { active--; waiting.shift()?.(); }
  };
}
