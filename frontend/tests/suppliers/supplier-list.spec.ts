// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the supplier browse page (search, filters, sort, pagination, errors).
// Reviewed by authors.
import { expect, test } from "@playwright/test";
import {
  ADMIN_PROFILE,
  fakeJwt,
  mockApi,
  seedToken,
  type MockApi,
} from "../support/api-mocks";
import { makeSupplier, supplierList } from "../support/suppliers";

function expectListQuery(
  api: MockApi,
  expected: Record<string, string[]>,
): Promise<void> {
  return expect
    .poll(() => api.lastCall("GET", "/api/suppliers")?.query)
    .toMatchObject(expected);
}

test.describe("supplier list", () => {
  test("renders cards after loading and opens the detail view", async ({
    page,
  }) => {
    const coffee = makeSupplier();
    const bookshop = makeSupplier({
      id: "sup-2",
      name: "Book Haven",
      category: "Shopping",
      building: "Central Library",
      floor: null,
      startingTime: null,
      closingTime: null,
    });

    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers": async () => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { body: supplierList([coffee, bookshop]) };
      },
      "GET /api/suppliers/sup-1": () => ({ body: coffee }),
    });

    await page.goto("/suppliers");

    await expect(page.locator(".mantine-Loader-root")).toBeVisible();

    await expect(page.getByText("2 suppliers")).toBeVisible();
    await expect(page.getByText("Coffee Bean")).toBeVisible();
    await expect(page.getByText("COM3, Level 1")).toBeVisible();
    await expect(page.getByText("08:00 – 20:00")).toBeVisible();
    // Clients get no management shortcut.
    await expect(
      page.getByRole("button", { name: "Add supplier" }),
    ).toHaveCount(0);

    await page.getByRole("link", { name: /Coffee Bean/ }).click();
    await expect(page).toHaveURL(/\/suppliers\/sup-1$/);
    await expect(
      page.getByRole("heading", { name: "Coffee Bean" }),
    ).toBeVisible();
  });

  test("shows an empty state when nothing matches", async ({ page }) => {
    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers": () => ({ body: supplierList([]) }),
    });

    await page.goto("/suppliers");

    await expect(page.getByText("0 suppliers")).toBeVisible();
    await expect(
      page.getByText("No suppliers match your filters."),
    ).toBeVisible();
  });

  test("sends search, category, zone and sort parameters", async ({ page }) => {
    await seedToken(page);
    const api = await mockApi(page, {
      "GET /api/suppliers": () => ({ body: supplierList([makeSupplier()]) }),
    });

    await page.goto("/suppliers");
    await expect(page.getByText("Coffee Bean")).toBeVisible();

    await page.getByPlaceholder("Search suppliers...").fill("coffee");
    await expectListQuery(api, { q: ["coffee"], page: ["1"] });

    await page.getByPlaceholder("All categories").click();
    await page.getByRole("option", { name: "Food", exact: true }).click();
    await expectListQuery(api, { category: ["Food"], q: ["coffee"] });

    await page.getByPlaceholder("Filter by building / zone").fill("COM3");
    await expectListQuery(api, { zone: ["COM3"] });

    await page.getByText("Building", { exact: true }).click();
    await expectListQuery(api, { sort: ["building"], page: ["1"] });

    await page.getByText("Desc", { exact: true }).click();
    await expectListQuery(api, { sort: ["building"], order: ["desc"] });
  });

  test("requests the next page of results", async ({ page }) => {
    await seedToken(page);
    const items = Array.from({ length: 12 }, (_, index) =>
      makeSupplier({ id: `sup-${index + 1}`, name: `Supplier ${index + 1}` }),
    );
    const api = await mockApi(page, {
      "GET /api/suppliers": () => ({
        body: supplierList(items, { total: 30 }),
      }),
    });

    await page.goto("/suppliers");
    await expect(page.getByText("Supplier 1", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "2", exact: true }).click();
    await expectListQuery(api, { page: ["2"], page_size: ["12"] });
  });

  test("shows a gateway error without losing the page", async ({ page }) => {
    await seedToken(page);
    await mockApi(page, {
      "GET /api/suppliers": () => ({
        status: 503,
        body: {
          code: "unavailable",
          message: "Supplier service unavailable",
        },
      }),
    });

    await page.goto("/suppliers");

    await expect(page.getByRole("alert")).toContainText(
      "Supplier service unavailable",
    );
    await expect(page.getByRole("heading", { name: "Campus Suppliers" })).toBeVisible();
  });

  test("shows the add-supplier shortcut to admins", async ({ page }) => {
    await seedToken(page, fakeJwt({ role: "admin" }));
    await mockApi(page, {
      "GET /api/users/me": () => ({ body: ADMIN_PROFILE }),
      "GET /api/suppliers": () => ({ body: supplierList([]) }),
    });

    await page.goto("/suppliers");
    await page.getByRole("button", { name: "Add supplier" }).click();

    await expect(page).toHaveURL(/\/admin\/suppliers$/);
  });
});
