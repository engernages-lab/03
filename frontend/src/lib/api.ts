/**
 * Typed API client.
 *
 * All backend failures use the `{ error: { code, message, details, request_id } }`
 * envelope, which is surfaced as an `ApiError` so the UI can render actionable
 * messages instead of `[object Object]`.
 */

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
export const API_BASE = RAW_BASE.replace(/\/$/, "");
export const API_V1 = `${API_BASE}/api/v1`;

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || `请求失败 (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code;
    this.details = payload.details;
    this.requestId = payload.request_id;
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_V1}${path}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorPayload = { code: `HTTP_${response.status}`, message: response.statusText };
  try {
    const body = await response.json();
    if (body?.error) payload = body.error as ApiErrorPayload;
  } catch {
    /* non JSON error body - keep status text */
  }
  return new ApiError(response.status, payload);
}

async function request<T>(path: string, init: RequestInit = {}, query?: Query): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
      credentials: "same-origin",
    });
  } catch (cause) {
    throw new ApiError(0, {
      code: "NETWORK_ERROR",
      message: "无法连接后端服务，请确认 API 服务已启动。",
      details: { cause: String(cause) },
    });
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>(path, { method: "GET" }, query),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string, query?: Query) => request<T>(path, { method: "DELETE" }, query),
  upload: <T>(path: string, form: FormData, query?: Query) =>
    request<T>(path, { method: "POST", body: form }, query),
};

/** Absolute URL for a backend-served static asset (artwork, audio stream...). */
export function staticUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}
