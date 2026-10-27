// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the supplier detail page. Reviewed by authors.
import { expect, test } from "@playwright/test";
import {
  ADMIN_PROFILE,
  fakeJwt,
  mockApi,
  seedToken,
} from "../support/api-mocks";
import { makeSupplier, supplierList } from "../support/suppliers";

test.describe("supplier detail", () => {
  test("renders the full supplier record for clients", async ({ page }) => {
    const supplier = makeSupplier();
    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers/sup-1": () => ({ body: supplier }),
      "GET /api/suppliers": () => ({ body: supplierList([supplier]) }),
    });

    await page.goto("/suppliers/sup-1");

    await expect(
      page.getByRole("heading", { name: "Coffee Bean" }),
    ).toBeVisible();
    await expect(page.getByText("Food/Coffee")).toBeVisible();
    await expect(page.getByText("Active", { exact: true })).toBeVisible();
    await expect(page.getByText("COM3")).toBeVisible();
    await expect(page.getByText("Level 1")).toBeVisible();
    await expect(page.getByText("Near the entrance")).toBeVisible();
    await expect(page.getByText("08:00 – 20:00")).toBeVisible();
    await expect(page.getByText("1.2940156, 103.7738478")).toBeVisible();
    // Management actions are admin-only UX.
    await expect(
      page.getByRole("button", { name: "Edit / Manage" }),
    ).toHaveCount(0);

    await page.getByRole("link", { name: /Back to suppliers/ }).click();
    await expect(page).toHaveURL(/\/suppliers$/);
  });

  test("renders placeholders for optional fields that are missing", async ({
    page,
  }) => {
    const supplier = makeSupplier({
      id: "sup-min",
      name: "Minimal Kiosk",
      floor: null,
      locationDescription: null,
      latitude: null,
      longitude: null,
      startingTime: null,
      closingTime: null,
    });
    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers/sup-min": () => ({ body: supplier }),
    });

    await page.goto("/suppliers/sup-min");

    await expect(
      page.getByRole("heading", { name: "Minimal Kiosk" }),
    ).toBeVisible();
    // Floor, Location, Opening hours and Coordinates all fall back to "—".
    await expect(page.getByText("—")).toHaveCount(4);
  });

  test("surfaces a 404 for an unknown supplier", async ({ page }) => {
    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers/missing": () => ({
        status: 404,
        body: {
          code: "not_found",
          message: "Supplier 'missing' was not found.",
        },
      }),
    });

    await page.goto("/suppliers/missing");

    await expect(page.getByRole("alert")).toContainText(
      "Supplier 'missing' was not found.",
    );
    await expect(
      page.getByRole("link", { name: /Back to suppliers/ }),
    ).toBeVisible();
  });

  test("deep-links admins into the edit form", async ({ page }) => {
    await seedToken(page, fakeJwt({ role: "admin" }));
    await mockApi(page, {
      "GET /api/users/me": () => ({ body: ADMIN_PROFILE }),
      "GET /api/suppliers/sup-1": () => ({ body: makeSupplier() }),
      "GET /api/suppliers": () => ({ body: supplierList([]) }),
    });

    await page.goto("/suppliers/sup-1");
    await page.getByRole("button", { name: "Edit / Manage" }).click();

    await expect(page).toHaveURL(/\/admin\/suppliers$/);
    await expect(
      page.getByRole("heading", { name: "Edit supplier" }),
    ).toBeVisible();
    await expect(page.getByLabel("Name")).toHaveValue("Coffee Bean");
  });
});
