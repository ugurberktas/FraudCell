import type { ApiEnvelope } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/gateway/${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiError(0, "SERVICE_UNAVAILABLE", "Servise ulasilamiyor");
  }

  let body: ApiEnvelope<T>;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(response.status, `HTTP_${response.status}`, "Gecersiz servis yaniti");
  }

  if (!response.ok || !body.success) {
    const apiError = body.error || { code: `HTTP_${response.status}`, message: "Islem basarisiz", details: {} };
    throw new ApiError(response.status, apiError.code, apiError.message, apiError.details || {});
  }
  return body.data;
}

export function authHeader(token: string) {
  return { Authorization: `Bearer ${token}` };
}
