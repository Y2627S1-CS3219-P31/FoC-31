// AI-assisted (OpenCode + Claude): regression tests for session handling and
// the authenticated/admin route guards. Reviewed by authors.
import { expect, test } from "@playwright/test";
import {
  ADMIN_PROFILE,
  fakeJwt,
  mockApi,
  seedToken,
  storedToken,
} from "../support/api-mocks";

test.describe("auth session", () => {
  test("redirects anonymous visitors from protected pages to login", async ({
    page,
  }) => {
    await mockApi(page);
    await page.goto("/suppliers");

    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
  });

  test("hydrates the session from a stored token without logging in again", async ({
    page,
  }) => {
    await seedToken(page);
    const api = await mockApi(page);

    await page.goto("/suppliers");

    await expect(page).toHaveURL(/\/suppliers$/);
    await expect(page.getByText("Client", { exact: true })).toBeVisible();
    expect(api.callsTo("POST", "/api/users/login")).toHaveLength(0);
    expect(api.lastCall("GET", "/api/users/me")?.authorization).toBe(
      `Bearer ${await storedToken(page)}`,
    );
  });

  test("clears an expired token and returns to login", async ({ page }) => {
    await seedToken(page, fakeJwt({ role: "client", exp: 0 }));
    await mockApi(page, {
      "GET /api/users/me": () => ({
        status: 401,
        body: { code: "invalid_token", message: "Not authenticated" },
      }),
    });

    await page.goto("/suppliers");

    await expect(page).toHaveURL(/\/login$/);
    expect(await storedToken(page)).toBeNull();
  });

  test("logs out, clears the token and re-protects pages", async ({ page }) => {
    await seedToken(page);
    await mockApi(page);

    await page.goto("/suppliers");
    await expect(page).toHaveURL(/\/suppliers$/);

    await page.getByRole("button", { name: "Log out" }).click();

    await expect(page).toHaveURL(/\/login$/);
    expect(await storedToken(page)).toBeNull();

    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("keeps clients out of admin-only routes", async ({ page }) => {
    await seedToken(page);
    await mockApi(page);

    await page.goto("/admin/suppliers");

    await expect(page).toHaveURL(/\/suppliers$/);
    await expect(
      page.getByRole("link", { name: "Manage Suppliers" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Client Accounts" }),
    ).toHaveCount(0);
  });

  test("lets admins into admin-only routes", async ({ page }) => {
    await seedToken(page, fakeJwt({ role: "admin" }));
    const api = await mockApi(page, {
      "GET /api/users/me": () => ({ body: ADMIN_PROFILE }),
    });

    await page.goto("/admin/clients");

    await expect(page).toHaveURL(/\/admin\/clients$/);
    await expect(page.getByText("Admin", { exact: true })).toBeVisible();
    expect(api.lastCall("GET", "/api/users/admin")).not.toBeUndefined();
  });
});
