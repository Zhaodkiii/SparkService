import http from '../../../shared/api/http';
import type { SharePublicPayload } from '../types';

export function fetchSharePayload(code: string) {
  return http.get<unknown, SharePublicPayload>(
    `/api/v1/medical/shares/public/${encodeURIComponent(code)}/`,
  );
}
