// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): shared Playwright
// helpers that fake the API gateway for frontend auth regression tests.
// Reviewed by authors.
import type { Page, Request, Route } from "@playwright/test";

export const TOKEN_KEY = "foc.token";

export interface Profile {
  id: string;
  email: string;
  display_name: string;
  contact_number: string | null;
  role: "admin" | "client";
  email_verified: boolean;
}

export const CLIENT_PROFILE: Profile = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "e0123456@u.nus.edu",
  display_name: "Ada Lovelace",
  contact_number: null,
  role: "client",
  email_verified: true,
};

export const ADMIN_PROFILE: Profile = {
  id: "22222222-2222-2222-2222-222222222222",
  email: "e0000001@u.nus.edu",
  display_name: "Grace Hopper",
  contact_number: "91234567",
  role: "admin",
  email_verified: true,
};

function base64Url(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

/** Builds an unsigned JWT-shaped token; the app only reads the `role` claim. */
export function fakeJwt(claims: Record<string, unknown> = { role: "client" }): string {
  return [
    base64Url({ alg: "HS256", typ: "JWT" }),
    base64Url(claims),
    "test-signature",
  ].join(".");
}

export interface MockResponse {
  status?: number;
  body?: unknown;
  /** Simulate a transport failure (gateway unreachable). */
  abort?: boolean;
}

export type Responder = (
  request: Request,
  body: Record<string, unknown> | null,
) => MockResponse | Promise<MockResponse>;

export interface MockCall {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
  authorization: string | null;
}

export interface MockApi {
  /** Every request the app made (method + path), in order. */
  calls: MockCall[];
  callsTo(method: string, path: string): MockCall[];
  lastCall(method: string, path: string): MockCall | undefined;
}

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
  "access-control-allow-headers": "content-type, authorization",
};

const JSON_HEADERS = { ...CORS_HEADERS, "content-type": "application/json" };

const DEFAULT_RESPONSES: Record<string, Responder> = {
  "POST /api/users/login": () => ({
    body: { access_token: fakeJwt(), token_type: "bearer", expires_in: 3600 },
  }),
  "GET /api/users/me": () => ({ body: CLIENT_PROFILE }),
  "POST /api/users/register": () => ({
    status: 201,
    body: {
      id: "33333333-3333-3333-3333-333333333333",
      email: CLIENT_PROFILE.email,
      message: "verification required",
    },
  }),
  "POST /api/users/otp/verify": () => ({ body: { verified: true } }),
  "POST /api/users/otp/resend": () => ({ body: { message: "sent" } }),
  "GET /api/suppliers": () => ({
    body: { items: [], page: 1, pageSize: 12, total: 0 },
  }),
  "GET /api/users/admin": () => ({
    body: { items: [], total: 0, limit: 50, offset: 0 },
  }),
};

/**
 * Intercepts every `/api/**` call and answers it from an in-memory router.
 * Pass `overrides` keyed by `"METHOD /path"` to change a response per test.
 * Unknown endpoints fail with 404 so missing mocks surface as test failures.
 */
export async function mockApi(
  page: Page,
  overrides: Record<string, Responder> = {},
): Promise<MockApi> {
  const responders: Record<string, Responder> = {
    ...DEFAULT_RESPONSES,
    ...overrides,
  };
  const calls: MockCall[] = [];

  await page.route("**/api/**", async (route: Route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;

    // Cross-origin JSON calls trigger a CORS preflight; answer it directly.
    if (method === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }

    const raw = request.postData();
    let body: Record<string, unknown> | null = null;
    if (raw) {
      try {
        body = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        body = { raw };
      }
    }

    calls.push({
      method,
      path,
      body,
      authorization: request.headers()["authorization"] ?? null,
    });

    const responder = responders[`${method} ${path}`];
    if (!responder) {
      await route.fulfill({
        status: 404,
        headers: JSON_HEADERS,
        body: JSON.stringify({
          code: "mock_not_found",
          message: `No mock for ${method} ${path}`,
        }),
      });
      return;
    }

    const response = await responder(request, body);
    if (response.abort) {
      await route.abort("connectionrefused");
      return;
    }

    await route.fulfill({
      status: response.status ?? 200,
      headers: JSON_HEADERS,
      body: response.body === undefined ? "" : JSON.stringify(response.body),
    });
  });

  const callsTo = (method: string, path: string) =>
    calls.filter((call) => call.method === method && call.path === path);

  return {
    calls,
    callsTo,
    lastCall: (method: string, path: string) => {
      const matches = callsTo(method, path);
      return matches[matches.length - 1];
    },
  };
}

/**
 * Stores a session token once, before navigating to a protected page.
 * (One-shot on purpose: a test can log out and reload without the token
 * being re-seeded behind its back.)
 */
export async function seedToken(page: Page, token = fakeJwt()): Promise<void> {
  if (!page.url().startsWith("http")) {
    await page.goto("/login");
  }
  await page.evaluate(
    ([key, value]: [string, string]) => {
      window.localStorage.setItem(key, value);
    },
    [TOKEN_KEY, token] as [string, string],
  );
}

/** Reads the app's persisted bearer token from localStorage. */
export async function storedToken(page: Page): Promise<string | null> {
  return page.evaluate((key) => window.localStorage.getItem(key), TOKEN_KEY);
}
