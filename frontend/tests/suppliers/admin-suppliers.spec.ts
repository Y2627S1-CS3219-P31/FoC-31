// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the admin supplier management screen (list, create, edit, deactivate,
// reactivate). Reviewed by authors.
import { expect, test, type Page } from "@playwright/test";
import {
  ADMIN_PROFILE,
  fakeJwt,
  mockApi,
  seedToken,
  type Responder,
} from "../support/api-mocks";
import { makeSupplier, supplierList } from "../support/suppliers";

async function openAdminSuppliers(
  page: Page,
  overrides: Record<string, Responder> = {},
) {
  await seedToken(page, fakeJwt({ role: "admin" }));
  const api = await mockApi(page, {
    "GET /api/users/me": () => ({ body: ADMIN_PROFILE }),
    "GET /api/suppliers": () => ({ body: supplierList([]) }),
    ...overrides,
  });
  await page.goto("/admin/suppliers");
  return api;
}

async function fillNewSupplierForm(
  page: Page,
  values: { name?: string; openingTime?: string } = {},
) {
  await page.getByLabel("Name").fill(values.name ?? "Cool Spot");
  // Scope to the textbox: once opened, the dropdown listbox also references
  // the "Category" label via aria-labelledby.
  await page.getByRole("textbox", { name: /Category/ }).click();
  await page.getByRole("option", { name: "Food", exact: true }).click();
  await page.getByLabel("Campus location (building)").fill("COM2");
  await page.getByLabel("Floor").fill("1");
  await page.getByLabel("Opening time").fill(values.openingTime ?? "09:00");
  await page.getByLabel("Closing time").fill("21:30");
}

test.describe("admin suppliers", () => {
  test("lists suppliers and adds inactive ones on request", async ({ page }) => {
    const active = makeSupplier();
    const inactive = makeSupplier({
      id: "sup-2",
      name: "Old Kiosk",
      active: false,
    });
    const api = await openAdminSuppliers(page, {
      "GET /api/suppliers": (request) => {
        const includeInactive =
          new URL(request.url()).searchParams.get("include_inactive") === "true";
        return {
          body: supplierList(includeInactive ? [active, inactive] : [active], {
            pageSize: 10,
          }),
        };
      },
    });

    await expect(page.getByText("Coffee Bean")).toBeVisible();
    await expect(page.getByText("Old Kiosk")).toHaveCount(0);

    await page.getByText("Show inactive", { exact: true }).click();

    await expect(page.getByText("Old Kiosk")).toBeVisible();
    await expect(page.getByText("Inactive", { exact: true })).toBeVisible();
    await expect
      .poll(() => api.lastCall("GET", "/api/suppliers")?.query)
      .toMatchObject({ include_inactive: ["true"], page: ["1"] });
  });

  test("validates the form, then creates a normalized supplier", async ({
    page,
  }) => {
    const api = await openAdminSuppliers(page, {
      "POST /api/suppliers": () => ({
        status: 201,
        body: makeSupplier({ id: "sup-new", name: "Cool Spot" }),
      }),
    });

    await page.getByRole("button", { name: "New supplier" }).click();
    await expect(
      page.getByRole("heading", { name: "New supplier" }),
    ).toBeVisible();

    // Mandatory fields and time format are validated client-side.
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("Name is required")).toBeVisible();
    await expect(page.getByText("Category is required")).toBeVisible();
    await expect(page.getByText("Campus location is required")).toBeVisible();
    expect(api.callsTo("POST", "/api/suppliers")).toHaveLength(0);

    await fillNewSupplierForm(page, { name: "  Cool Spot  ", openingTime: "25:00" });
    await page.getByLabel("Latitude").fill("1.294016");
    await page.getByLabel("Longitude").fill("103.7738");
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("Use HH:MM (24h)")).toBeVisible();
    expect(api.callsTo("POST", "/api/suppliers")).toHaveLength(0);

    await page.getByLabel("Opening time").fill("09:00");
    await page.getByRole("button", { name: "Create" }).click();

    await expect(page.getByText("Supplier created")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "New supplier" }),
    ).toHaveCount(0);

    expect(api.lastCall("POST", "/api/suppliers")?.body).toEqual({
      name: "Cool Spot",
      category: "Food",
      building: "COM2",
      floor: "1",
      locationDescription: null,
      latitude: 1.294016,
      longitude: 103.7738,
      startingTime: "09:00",
      closingTime: "21:30",
      imageUrl: null,
    });
  });

  test("edits an existing supplier", async ({ page }) => {
    const supplier = makeSupplier();
    const api = await openAdminSuppliers(page, {
      "GET /api/suppliers": () => ({
        body: supplierList([supplier], { pageSize: 10 }),
      }),
      "PATCH /api/suppliers/sup-1": () => ({
        body: { ...supplier, name: "Coffee Bean 2" },
      }),
    });

    await page.getByRole("button", { name: "Edit Coffee Bean" }).click();
    await expect(
      page.getByRole("heading", { name: "Edit supplier" }),
    ).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Coffee Bean");

    await page.getByLabel("Name").fill("Coffee Bean 2");
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("Supplier updated")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Edit supplier" }),
    ).toHaveCount(0);
    expect(api.lastCall("PATCH", "/api/suppliers/sup-1")?.body).toMatchObject({
      name: "Coffee Bean 2",
      category: "Food/Coffee",
      building: "COM3",
    });
  });

  test("deactivates a supplier after confirmation", async ({ page }) => {
    const supplier = makeSupplier();
    const api = await openAdminSuppliers(page, {
      "GET /api/suppliers": () => ({
        body: supplierList([supplier], { pageSize: 10 }),
      }),
      "POST /api/suppliers/sup-1/deactivate": () => ({
        body: { ...supplier, active: false },
      }),
    });

    await page.getByRole("button", { name: "Edit Coffee Bean" }).click();
    await page.getByRole("button", { name: "Deactivate" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Deactivate supplier?")).toBeVisible();
    await dialog.getByRole("button", { name: "Deactivate" }).click();

    await expect(page.getByText("Supplier deactivated")).toBeVisible();
    await expect(dialog).toHaveCount(0);
    expect(
      api.lastCall("POST", "/api/suppliers/sup-1/deactivate"),
    ).not.toBeUndefined();
  });

  test("reactivates an inactive supplier", async ({ page }) => {
    const inactive = makeSupplier({
      id: "sup-2",
      name: "Old Kiosk",
      active: false,
    });
    const api = await openAdminSuppliers(page, {
      "GET /api/suppliers": () => ({
        body: supplierList([makeSupplier(), inactive], { pageSize: 10 }),
      }),
      "POST /api/suppliers/sup-2/reactivate": () => ({
        body: { ...inactive, active: true },
      }),
    });

    await page.getByRole("button", { name: "Reactivate Old Kiosk" }).click();

    await expect(page.getByText("Supplier reactivated")).toBeVisible();
    expect(
      api.lastCall("POST", "/api/suppliers/sup-2/reactivate"),
    ).not.toBeUndefined();
  });

  test("keeps the form open when the gateway rejects the save", async ({
    page,
  }) => {
    const api = await openAdminSuppliers(page, {
      "POST /api/suppliers": () => ({
        status: 422,
        body: {
          code: "validation_error",
          message: "category must be one of the allowed values",
        },
      }),
    });

    await page.getByRole("button", { name: "New supplier" }).click();
    await fillNewSupplierForm(page);
    await page.getByRole("button", { name: "Create" }).click();

    await expect(
      page.getByText("category must be one of the allowed values"),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "New supplier" }),
    ).toBeVisible();
    expect(api.callsTo("POST", "/api/suppliers")).toHaveLength(1);
  });
});
