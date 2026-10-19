// AI-assisted (OpenCode + Claude): typed fetch wrapper for the API gateway,
// attaches the JWT bearer token and normalizes error payloads. Extended with
// ordersApi and creditsApi for D3. Reviewed by authors.
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
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (extraHeaders) Object.assign(headers, extraHeaders);

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
  list(
    params: {
      limit?: number;
      offset?: number;
      q?: string;
      status?: "active" | "suspended";
    } = {},
  ) {
    const { limit = 50, offset = 0, q, status } = params;
    return request<AdminUserList>(
      "GET",
      `/api/users/admin${buildQuery({ limit, offset, q, status })}`,
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
  updateRole(userId: string, role: "admin" | "client") {
    return request<AdminUser>("PATCH", `/api/users/admin/${userId}/role`, {
      role,
    });
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
        page_size: query.pageSize,
        sort: query.sort,
        order: query.order,
        include_inactive: query.includeInactive,
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
  reactivate(id: string) {
    return request<Supplier>("POST", `/api/suppliers/${id}/reactivate`);
  },
};

// ---- Orders ----
export type OrderStatus =
  | "OPEN"
  | "ACCEPTED"
  | "PICKED_UP"
  | "AWAITING_APPROVAL"
  | "COMPLETED"
  | "CANCELLED"
  | "EXPIRED";

export interface OrderResponse {
  order_id: string;
  name: string;
  details: string;
  reward: number;
  deadline: string;
  supplier_id: string;
  requester_id: string;
  courier_id: string | null;
  pickup_location: string;
  delivery_location: string;
  status: OrderStatus;
  created_at: string;
}

export interface OrderCreate {
  name: string;
  details: string;
  reward: number;
  deadline: string;
  supplier_id: string;
  pickup_location: string;
  delivery_location: string;
}

export interface OrderUpdate extends OrderCreate {}

export interface OrderCancellationRequest {
  reason: string;
}

export interface OrderActionResponse {
  task_id: string;
  order_id: string;
  status: string;
  failure_reason: string | null;
}

export interface OrderTaskResult {
  task_id: string;
  order_id: string;
  status: string;
  failure_reason: string | null;
}

export const ordersApi = {
  list(
    params: {
      category?: string[];
      min_reward?: number;
      max_reward?: number;
      sort_by?: string;
      sort_order?: string;
    } = {},
  ) {
    return request<OrderResponse[]>(
      "GET",
      `/api/orders${buildQuery(params as Record<string, unknown>)}`,
    );
  },
  get(id: string) {
    return request<OrderResponse>("GET", `/api/orders/${id}`);
  },
  create(body: OrderCreate) {
    return request<OrderResponse>("POST", "/api/orders", body);
  },
  update(id: string, body: OrderUpdate) {
    return request<OrderActionResponse>("PATCH", `/api/orders/${id}`, body);
  },
  delete(id: string) {
    return request<OrderActionResponse>("DELETE", `/api/orders/${id}`);
  },
  accept(id: string) {
    return request<OrderResponse>("POST", `/api/orders/${id}/accept`);
  },
  pickup(id: string) {
    return request<OrderResponse>("POST", `/api/orders/${id}/pickup`);
  },
  deliver(id: string) {
    return request<OrderResponse>("POST", `/api/orders/${id}/deliver`);
  },
  withdraw(id: string) {
    return request<OrderResponse>(
      "POST",
      `/api/orders/${id}/withdraw`,
      undefined,
      { "Idempotency-Key": crypto.randomUUID() },
    );
  },
  approve(id: string) {
    return request<OrderActionResponse>("POST", `/api/orders/${id}/approve`);
  },
  cancel(id: string, body: OrderCancellationRequest) {
    return request<OrderActionResponse>(
      "POST",
      `/api/orders/${id}/cancel`,
      body,
    );
  },
  requestedOngoing() {
    return request<OrderResponse[]>("GET", "/api/orders/requested/ongoing");
  },
  requestedCompleted() {
    return request<OrderResponse[]>("GET", "/api/orders/requested/completed");
  },
  assignedActive() {
    return request<OrderResponse[]>("GET", "/api/orders/assigned");
  },
  assignedCompleted() {
    return request<OrderResponse[]>("GET", "/api/orders/assigned/completed");
  },
  pollUpdate(taskId: string) {
    return request<OrderActionResponse>(
      "GET",
      `/api/orders/updates/${taskId}`,
    );
  },
  pollDeletion(taskId: string) {
    return request<OrderActionResponse>(
      "GET",
      `/api/orders/deletions/${taskId}`,
    );
  },
};

// ---- Credits ----
export interface BalanceResponse {
  user_id: string;
  available_balance: number;
  reserved_balance: number;
}

export interface TransactionResponse {
  id: string;
  kind: string;
  amount: number;
  counterparty_user_id: string | null;
  reservation_id: string | null;
  order_id: string | null;
  created_at: string;
}

export const creditsApi = {
  getBalance(userId: string) {
    return request<BalanceResponse>("GET", `/api/credits/${userId}/balance`);
  },
  getTransactions(userId: string) {
    return request<TransactionResponse[]>(
      "GET",
      `/api/credits/${userId}/transactions`,
    );
  },
};
