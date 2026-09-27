// AI-assisted (OpenCode + Claude): typed fetch wrapper for the API gateway,
// attaches the JWT bearer token and normalizes error payloads. Reviewed by authors.
import type {
  AdminUser,
  AdminUserList,
  LoginResponse,
  ProfileResponse,
  RegisterResponse,
  Supplier,
  SupplierCreate,
  SupplierList,
  SupplierQuery,
  SupplierUpdate,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";

const TOKEN_KEY = "foc.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const { message, code } = extractError(payload, res.status);
    throw new ApiError(res.status, message, code);
  }

  return payload as T;
}

function extractError(
  payload: unknown,
  status: number,
): { message: string; code?: string } {
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    // Gateway style: { code, message }
    if (typeof obj.message === "string") {
      return { message: obj.message, code: obj.code as string | undefined };
    }
    // FastAPI style: { detail: string | [{ msg }] }
    const detail = obj.detail;
    if (typeof detail === "string") return { message: detail };
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as Record<string, unknown>;
      if (typeof first?.msg === "string") return { message: first.msg };
    }
  }
  if (typeof payload === "string" && payload) return { message: payload };
  return { message: `Request failed (${status})` };
}

function buildQuery(params: Record<string, unknown>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) usp.append(key, String(v));
    } else {
      usp.append(key, String(value));
    }
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

// ---- Auth / users ----
export const authApi = {
  register(body: {
    email: string;
    password: string;
    display_name: string;
    contact_number?: string | null;
  }) {
    return request<RegisterResponse>("POST", "/api/users/register", body);
  },
  verifyOtp(email: string, code: string) {
    return request<{ verified: boolean }>("POST", "/api/users/otp/verify", {
      email,
      code,
    });
  },
  resendOtp(email: string) {
    return request<unknown>("POST", "/api/users/otp/resend", { email });
  },
  login(email: string, password: string) {
    return request<LoginResponse>("POST", "/api/users/login", {
      email,
      password,
    });
  },
  me() {
    return request<ProfileResponse>("GET", "/api/users/me");
  },
  updateMe(body: {
    display_name?: string;
    contact_number?: string | null;
  }) {
    return request<ProfileResponse>("PATCH", "/api/users/me", body);
  },
};

// ---- Admin user management ----
export const adminUsersApi = {
  list(limit = 50, offset = 0) {
    return request<AdminUserList>(
      "GET",
      `/api/users/admin${buildQuery({ limit, offset })}`,
    );
  },
  createAdmin(body: {
    email: string;
    password: string;
    display_name: string;
    contact_number?: string | null;
  }) {
    return request<AdminUser>("POST", "/api/users/admin", body);
  },
  suspend(userId: string) {
    return request<AdminUser>("POST", `/api/users/admin/${userId}/suspend`);
  },
  unsuspend(userId: string) {
    return request<AdminUser>("POST", `/api/users/admin/${userId}/unsuspend`);
  },
};

// ---- Suppliers ----
export const suppliersApi = {
  list(query: SupplierQuery = {}) {
    return request<SupplierList>(
      "GET",
      `/api/suppliers${buildQuery({
        category: query.category,
        zone: query.zone,
        q: query.q,
        page: query.page,
        pageSize: query.pageSize,
      })}`,
    );
  },
  get(id: string) {
    return request<Supplier>("GET", `/api/suppliers/${id}`);
  },
  create(body: SupplierCreate) {
    return request<Supplier>("POST", "/api/suppliers", body);
  },
  update(id: string, body: SupplierUpdate) {
    return request<Supplier>("PATCH", `/api/suppliers/${id}`, body);
  },
  deactivate(id: string) {
    return request<Supplier>("POST", `/api/suppliers/${id}/deactivate`);
  },
};
