// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the profile screen (read-only account fields, editable name/contact).
// Reviewed by authors.
import { expect, test } from "@playwright/test";
import { CLIENT_PROFILE, mockApi, seedToken } from "../support/api-mocks";

test.describe("profile", () => {
  test("shows read-only account fields and saves an update", async ({
    page,
  }) => {
    let current = CLIENT_PROFILE;
    await seedToken(page);
    const api = await mockApi(page, {
      "GET /api/users/me": () => ({ body: current }),
      "PATCH /api/users/me": (_request, body) => {
        current = {
          ...CLIENT_PROFILE,
          display_name: body?.display_name as string,
          contact_number: body?.contact_number as string | null,
        };
        return { body: current };
      },
    });

    await page.goto("/profile");

    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
    await expect(page.getByText(CLIENT_PROFILE.email)).toBeVisible();
    await expect(page.getByText("client", { exact: true })).toBeVisible();
    await expect(page.getByText("Yes", { exact: true })).toBeVisible();
    // Only display name and contact number are editable.
    await expect(page.getByRole("textbox")).toHaveCount(2);
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Lovelace");

    await page.getByLabel("Display name").fill("  Ada Tan  ");
    await page.getByLabel("Contact number").fill("81234567");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByText("Profile updated")).toBeVisible();
    expect(api.lastCall("PATCH", "/api/users/me")?.body).toEqual({
      display_name: "Ada Tan",
      contact_number: "81234567",
    });
    // The provider refreshes from the gateway, so the form shows new values.
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Tan");
    await expect(page.getByLabel("Contact number")).toHaveValue("81234567");
  });

  test("validates the editable fields before calling the API", async ({
    page,
  }) => {
    await seedToken(page);
    const api = await mockApi(page);

    await page.goto("/profile");
    await page.getByLabel("Display name").fill("");
    await page.getByLabel("Contact number").fill("12345678");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByText("Display name required")).toBeVisible();
    await expect(page.getByText("SG mobile: 8 digits")).toBeVisible();
    expect(api.callsTo("PATCH", "/api/users/me")).toHaveLength(0);
  });

  test("clears the optional contact number", async ({ page }) => {
    await seedToken(page);
    const api = await mockApi(page, {
      "GET /api/users/me": () => ({
        body: { ...CLIENT_PROFILE, contact_number: "91234567" },
      }),
      "PATCH /api/users/me": () => ({
        body: { ...CLIENT_PROFILE, contact_number: null },
      }),
    });

    await page.goto("/profile");
    await expect(page.getByLabel("Contact number")).toHaveValue("91234567");

    await page.getByLabel("Contact number").fill("");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(page.getByText("Profile updated")).toBeVisible();
    expect(api.lastCall("PATCH", "/api/users/me")?.body).toEqual({
      display_name: "Ada Lovelace",
      contact_number: null,
    });
  });

  test("shows a gateway error and keeps the entered values", async ({
    page,
  }) => {
    await seedToken(page);
    await mockApi(page, {
      "PATCH /api/users/me": () => ({
        status: 422,
        body: {
          code: "validation_error",
          message: "display_name must contain 1-50 characters",
        },
      }),
    });

    await page.goto("/profile");
    await page.getByLabel("Display name").fill("Ada Tan");
    await page.getByRole("button", { name: "Save changes" }).click();

    await expect(
      page.getByText("display_name must contain 1-50 characters"),
    ).toBeVisible();
    await expect(page.getByLabel("Display name")).toHaveValue("Ada Tan");
    await expect(page.getByLabel("Display name")).toBeEnabled();
  });
});
