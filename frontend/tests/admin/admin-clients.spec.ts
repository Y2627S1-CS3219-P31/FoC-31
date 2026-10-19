// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the admin client-accounts screen (list, filters, suspend, role changes,
// admin creation). Reviewed by authors.
import { expect, test, type Page } from "@playwright/test";
import {
  ADMIN_PROFILE,
  fakeJwt,
  mockApi,
  seedToken,
  type Responder,
  type MockApi,
} from "../support/api-mocks";
import { adminUserList, makeAdminUser } from "../support/admin-users";

const SELF = makeAdminUser({
  id: ADMIN_PROFILE.id,
  email: ADMIN_PROFILE.email,
  display_name: ADMIN_PROFILE.display_name,
  contact_number: ADMIN_PROFILE.contact_number,
  role: "admin",
});

async function openAdminClients(
  page: Page,
  overrides: Record<string, Responder> = {},
): Promise<MockApi> {
  await seedToken(page, fakeJwt({ role: "admin" }));
  const api = await mockApi(page, {
    "GET /api/users/me": () => ({ body: ADMIN_PROFILE }),
    "GET /api/users/admin": () => ({ body: adminUserList([SELF]) }),
    ...overrides,
  });
  await page.goto("/admin/clients");
  return api;
}

function expectUserQuery(
  api: MockApi,
  expected: Record<string, string[]>,
): Promise<void> {
  return expect
    .poll(() => api.lastCall("GET", "/api/users/admin")?.query)
    .toMatchObject(expected);
}

test.describe("admin clients", () => {
  test("lists accounts with role/status and marks the current admin", async ({
    page,
  }) => {
    const client = makeAdminUser();
    const demoAdmin = makeAdminUser({
      id: "user-3",
      email: "e0000002@u.nus.edu",
      display_name: "Alan Turing",
      role: "admin",
    });
    const api = await openAdminClients(page, {
      "GET /api/users/admin": () => ({
        body: adminUserList([SELF, client, demoAdmin]),
      }),
    });

    await expect(page.getByText("Grace Hopper")).toBeVisible();
    await expect(page.getByText("Ada Lovelace")).toBeVisible();

    const selfRow = page.getByRole("row", { name: /Grace Hopper/ });
    await expect(selfRow.getByText("You", { exact: true })).toBeVisible();
    await expect(selfRow.getByRole("button")).toHaveCount(0);

    const clientRow = page.getByRole("row", { name: /Ada Lovelace/ });
    await expect(
      clientRow.getByRole("button", { name: "Suspend" }),
    ).toBeVisible();
    await expect(
      clientRow.getByRole("button", { name: "Make admin" }),
    ).toBeVisible();

    // Other admins can be demoted, but not suspended.
    const adminRow = page.getByRole("row", { name: /Alan Turing/ });
    await expect(
      adminRow.getByRole("button", { name: "Demote to client" }),
    ).toBeVisible();
    await expect(
      adminRow.getByRole("button", { name: "Suspend" }),
    ).toHaveCount(0);

    expect(api.lastCall("GET", "/api/users/admin")?.query).toMatchObject({
      limit: ["20"],
      offset: ["0"],
    });
  });

  test("sends the search and status filters", async ({ page }) => {
    const api = await openAdminClients(page);

    await page.getByPlaceholder("Search by name or email...").fill("ada");
    await expectUserQuery(api, { q: ["ada"], offset: ["0"] });

    // The status Select is the only read-only combobox input on the page.
    const statusSelect = page.locator(
      'input[readonly][aria-haspopup="listbox"]',
    );
    await statusSelect.click();
    await page.getByRole("option", { name: "Suspended" }).click();
    await expectUserQuery(api, { status: ["suspended"], offset: ["0"] });

    await statusSelect.click();
    await page.getByRole("option", { name: "Status: All" }).click();
    await expect
      .poll(() => api.lastCall("GET", "/api/users/admin")?.query.status)
      .toBeUndefined();
  });

  test("suspends and reinstates an account", async ({ page }) => {
    let suspended = false;
    const client = () => makeAdminUser({ is_suspended: suspended });

    const api = await openAdminClients(page, {
      "GET /api/users/admin": () => ({ body: adminUserList([SELF, client()]) }),
      "POST /api/users/admin/user-1/suspend": () => {
        suspended = true;
        return { body: client() };
      },
      "POST /api/users/admin/user-1/unsuspend": () => {
        suspended = false;
        return { body: client() };
      },
    });

    const clientRow = page.getByRole("row", { name: /Ada Lovelace/ });

    await clientRow.getByRole("button", { name: "Suspend" }).click();
    await expect(page.getByText("Account suspended")).toBeVisible();
    await expect(
      clientRow.getByRole("button", { name: "Reinstate" }),
    ).toBeVisible();

    await clientRow.getByRole("button", { name: "Reinstate" }).click();
    await expect(page.getByText("Account reinstated")).toBeVisible();
    await expect(
      clientRow.getByRole("button", { name: "Suspend" }),
    ).toBeVisible();

    expect(
      api.lastCall("POST", "/api/users/admin/user-1/suspend"),
    ).not.toBeUndefined();
    expect(
      api.lastCall("POST", "/api/users/admin/user-1/unsuspend"),
    ).not.toBeUndefined();
  });

  test("promotes and demotes a user", async ({ page }) => {
    let role: "admin" | "client" = "client";
    const user = () => makeAdminUser({ role });

    const api = await openAdminClients(page, {
      "GET /api/users/admin": () => ({ body: adminUserList([SELF, user()]) }),
      "PATCH /api/users/admin/user-1/role": (_request, body) => {
        role = body?.role as "admin" | "client";
        return { body: user() };
      },
    });

    const row = page.getByRole("row", { name: /Ada Lovelace/ });

    await row.getByRole("button", { name: "Make admin" }).click();
    await expect(
      page.getByText("Ada Lovelace promoted to admin"),
    ).toBeVisible();
    expect(api.lastCall("PATCH", "/api/users/admin/user-1/role")?.body).toEqual({
      role: "admin",
    });

    await row.getByRole("button", { name: "Demote to client" }).click();
    await expect(
      page.getByText("Ada Lovelace demoted to client"),
    ).toBeVisible();
    expect(api.lastCall("PATCH", "/api/users/admin/user-1/role")?.body).toEqual({
      role: "client",
    });
  });

  test("validates and creates an administrator account", async ({ page }) => {
    const api = await openAdminClients(page, {
      "POST /api/users/admin": () => ({
        status: 201,
        body: makeAdminUser({
          id: "user-9",
          email: "e0999999@u.nus.edu",
          display_name: "New Admin",
          role: "admin",
        }),
      }),
    });

    await page.getByRole("button", { name: "Create admin account" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: "Create admin", exact: true }).click();
    await expect(dialog.getByText("Must be a @u.nus.edu address")).toBeVisible();
    await expect(
      dialog.getByText("At least 8 chars with letters and digits"),
    ).toBeVisible();
    await expect(dialog.getByText("Display name required")).toBeVisible();
    expect(api.callsTo("POST", "/api/users/admin")).toHaveLength(0);

    await dialog.getByLabel("NUS Email").fill("  E0999999@U.NUS.EDU ");
    await dialog.getByLabel("Display name").fill("  New Admin  ");
    await dialog.getByLabel("Contact number (optional)").fill("81234567");
    await dialog.getByLabel("Temporary password").fill("Password1");
    await dialog.getByRole("button", { name: "Create admin", exact: true }).click();

    await expect(page.getByText("Administrator created")).toBeVisible();
    await expect(dialog).toBeHidden();
    expect(api.lastCall("POST", "/api/users/admin")?.body).toEqual({
      email: "e0999999@u.nus.edu",
      password: "Password1",
      display_name: "New Admin",
      contact_number: "81234567",
    });
  });

  test("keeps the create dialog open when the gateway rejects it", async ({
    page,
  }) => {
    await openAdminClients(page, {
      "POST /api/users/admin": () => ({
        status: 409,
        body: { code: "email_taken", message: "Email already registered" },
      }),
    });

    await page.getByRole("button", { name: "Create admin account" }).click();
    const dialog = page.getByRole("dialog");

    await dialog.getByLabel("NUS Email").fill("e0999999@u.nus.edu");
    await dialog.getByLabel("Display name").fill("New Admin");
    await dialog.getByLabel("Temporary password").fill("Password1");
    await dialog.getByRole("button", { name: "Create admin", exact: true }).click();

    await expect(page.getByText("Email already registered")).toBeVisible();
    await expect(dialog).toBeVisible();
  });
});
