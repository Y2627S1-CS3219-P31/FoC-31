// AI-assisted (OpenCode + Claude): regression tests for the registration
// screen. Reviewed by authors.
import { expect, test } from "@playwright/test";
import { mockApi } from "../support/api-mocks";

test.describe("register", () => {
  test("validates NUS email, password strength, name and SG mobile", async ({
    page,
  }) => {
    const api = await mockApi(page);
    await page.goto("/register");

    await page.getByLabel("NUS Email").fill("someone@gmail.com");
    await page.getByLabel("Password").fill("short");
    await page.getByLabel("Contact number (optional)").fill("12345678");
    await page.getByRole("button", { name: "Sign Up" }).click();

    await expect(page.getByText("Must be a @u.nus.edu address")).toBeVisible();
    await expect(
      page.getByText("At least 8 chars with letters and digits"),
    ).toBeVisible();
    await expect(page.getByText("Display name required")).toBeVisible();
    await expect(
      page.getByText("SG mobile: 8 digits starting 8 or 9"),
    ).toBeVisible();
    expect(api.callsTo("POST", "/api/users/register")).toHaveLength(0);
  });

  test("registers a normalized payload and moves to OTP verification", async ({
    page,
  }) => {
    const api = await mockApi(page);
    await page.goto("/register");

    await page.getByLabel("NUS Email").fill("  E0123456@U.NUS.EDU  ");
    await page.getByLabel("Display name").fill("  Ada Lovelace  ");
    await page.getByLabel("Contact number (optional)").fill("91234567");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Sign Up" }).click();

    await expect(page).toHaveURL(/\/verify-otp$/);
    await expect(
      page.getByText("Account created. Check your email for a verification code."),
    ).toBeVisible();

    // The email is carried over to the OTP page in a normalized form.
    await expect(page.getByLabel("NUS Email")).toHaveValue(
      "e0123456@u.nus.edu",
    );

    expect(api.lastCall("POST", "/api/users/register")?.body).toEqual({
      email: "e0123456@u.nus.edu",
      password: "Password1",
      display_name: "Ada Lovelace",
      contact_number: "91234567",
    });
  });

  test("sends a null contact number when the optional field is blank", async ({
    page,
  }) => {
    const api = await mockApi(page);
    await page.goto("/register");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Display name").fill("Ada Lovelace");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Sign Up" }).click();

    await expect(page).toHaveURL(/\/verify-otp$/);
    expect(api.lastCall("POST", "/api/users/register")?.body).toMatchObject({
      contact_number: null,
    });
  });

  test("surfaces a duplicate-email error without leaving the form", async ({
    page,
  }) => {
    await mockApi(page, {
      "POST /api/users/register": () => ({
        status: 409,
        body: { code: "email_taken", message: "Email already registered" },
      }),
    });
    await page.goto("/register");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Display name").fill("Ada Lovelace");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Sign Up" }).click();

    await expect(page.getByText("Email already registered")).toBeVisible();
    await expect(page).toHaveURL(/\/register$/);
  });

  test("switches to the login tab", async ({ page }) => {
    await mockApi(page);
    await page.goto("/register");

    await page.getByRole("tab", { name: "Log In" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole("heading", { name: "Welcome back" }),
    ).toBeVisible();
  });
});
