// Wrapper fetch tối giản: gắn JWT, parse JSON, ném lỗi có thông điệp từ backend.
// Base URL lấy từ VITE_API_BASE, mặc định "/api" (proxy qua Vite khi dev).

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

const TOKEN_KEY = "threads_tool_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  // form = true -> gửi application/x-www-form-urlencoded (dùng cho /auth/login).
  form?: boolean;
  auth?: boolean;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form = false, auth = true } = opts;
  const headers: Record<string, string> = {};

  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      payload = new URLSearchParams(body as Record<string, string>).toString();
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  const resp = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });

  if (resp.status === 401) {
    setToken(null);
  }

  const text = await resp.text();
  const data = text ? JSON.parse(text) : null;

  if (!resp.ok) {
    const detail =
      (data && (data.detail || data.message)) || `Lỗi ${resp.status}`;
    throw new ApiError(resp.status, typeof detail === "string" ? detail : "Yêu cầu thất bại");
  }
  return data as T;
}
