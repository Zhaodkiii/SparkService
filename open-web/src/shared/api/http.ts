import axios, { AxiosError } from 'axios';

export interface ApiEnvelope<T> {
  code: number;
  msg: string | Record<string, unknown>;
  data: T;
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '';

const http = axios.create({
  baseURL,
  timeout: 15000,
});

function toDisplayError(error: AxiosError): Error {
  const body = error.response?.data as Record<string, unknown> | undefined;
  const msg = body?.msg;
  if (typeof msg === 'string' && msg) return new Error(msg);
  if (error.response?.status === 404) return new Error('not_found');
  if (error.message) return new Error(error.message);
  return new Error('request_failed');
}

http.interceptors.response.use(
  (response) => {
    const payload = response.data as ApiEnvelope<unknown>;
    if (payload && typeof payload.code === 'number') {
      if (payload.code !== 0) {
        return Promise.reject(
          new Error(typeof payload.msg === 'string' ? payload.msg : 'request_failed'),
        );
      }
      return payload.data;
    }
    return response.data;
  },
  (error: AxiosError) => Promise.reject(toDisplayError(error)),
);

export default http;
