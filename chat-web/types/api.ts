export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export interface SparkApiEnvelope<TData = unknown> {
  code: number;
  msg: string | Record<string, unknown>;
  data: TData | null;
}

export interface SparkApiFailure {
  ok: false;
  httpStatus: number;
  code: number;
  messageKey: string;
  message?: string;
  details?: unknown;
  requestId?: string;
  retryable: boolean;
}

export interface SparkApiSuccess<TData> {
  ok: true;
  data: TData;
  requestId?: string;
  httpStatus: number;
}

export type SparkApiResult<TData> = SparkApiSuccess<TData> | SparkApiFailure;

export interface SparkRequestOptions {
  signal?: AbortSignal;
  headers?: HeadersInit;
  body?: unknown;
  retryOnUnauthorized?: boolean;
  requestId?: string;
}

export interface SparkHttpClientOptions {
  baseUrl?: string;
  fetcher?: typeof fetch;
  getAccessToken?: () => string | null;
  refreshAccessToken?: () => Promise<string | null>;
}
