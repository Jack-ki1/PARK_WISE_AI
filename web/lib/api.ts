import { getApiKey } from "./auth";

export const API_BASE = "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiAuthError extends ApiError {
  constructor(message: string, status: number) {
    super(status, message);
    this.name = "ApiAuthError";
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  const key = getApiKey();
  if (key && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", key);
  }

  // Handle json payload
  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(path, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let errBody: unknown;
    try {
      errBody = await res.json();
      if (errBody && typeof errBody === "object" && "detail" in errBody) {
        detail = String((errBody as { detail: string }).detail);
      }
    } catch {
      // not JSON
    }

    if (res.status === 401 || res.status === 403) {
      throw new ApiAuthError(detail, res.status);
    }
    throw new ApiError(res.status, detail, errBody);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "POST", body: body as BodyInit }),
  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "PUT", body: body as BodyInit }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, { ...init, method: "PATCH", body: body as BodyInit }),
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "DELETE" }),
};
