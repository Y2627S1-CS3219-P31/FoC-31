// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the OTP verification screen. Reviewed by authors.
import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "../support/api-mocks";

const PIN_SELECTOR = 'input[autocomplete="one-time-code"]';

async function enterCode(page: Page, code: string): Promise<void> {
  const firstPin = page.locator(PIN_SELECTOR).first();
  await firstPin.click();
  await firstPin.pressSequentially(code);
}

test.describe("verify OTP", () => {
  test("requires an email and a complete 6-digit code", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto("/verify-otp");
    const validationToast = page
      .getByText("Enter email and 6-digit code")
      .last();

    await page.getByRole("button", { name: "Verify" }).click();
    await expect(validationToast).toBeVisible();

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await enterCode(page, "123");
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(validationToast).toBeVisible();

    expect(api.callsTo("POST", "/api/users/otp/verify")).toHaveLength(0);
  });

  test("submits the normalized email and code, then routes to login", async ({
    page,
  }) => {
    const api = await mockApi(page);
    await page.goto("/verify-otp");

    await page.getByLabel("NUS Email").fill("  E0123456@U.NUS.EDU ");
    await enterCode(page, "000123");
    await page.getByRole("button", { name: "Verify" }).click();

    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByText("Email verified — you can now log in."),
    ).toBeVisible();
    // Leading zeros must survive the PinInput round-trip.
    expect(api.lastCall("POST", "/api/users/otp/verify")?.body).toEqual({
      email: "e0123456@u.nus.edu",
      code: "000123",
    });
  });

  test("shows the gateway error for an invalid or expired code", async ({
    page,
  }) => {
    await mockApi(page, {
      "POST /api/users/otp/verify": () => ({
        status: 400,
        body: { code: "invalid_otp", message: "Invalid or expired code" },
      }),
    });
    await page.goto("/verify-otp");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await enterCode(page, "000000");
    await page.getByRole("button", { name: "Verify" }).click();

    await expect(page.getByText("Invalid or expired code")).toBeVisible();
    await expect(page).toHaveURL(/\/verify-otp$/);
  });

  test("allows a retry after an invalid code", async ({ page }) => {
    let attempts = 0;
    const api = await mockApi(page, {
      "POST /api/users/otp/verify": () => {
        attempts += 1;
        return attempts === 1
          ? {
              status: 400,
              body: {
                code: "invalid_otp",
                message: "Invalid or expired code",
              },
            }
          : { body: { verified: true } };
      },
    });
    await page.goto("/verify-otp");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await enterCode(page, "123456");

    const verify = page.getByRole("button", { name: "Verify" });
    await verify.click();
    await expect(page.getByText("Invalid or expired code")).toBeVisible();
    await expect(page).toHaveURL(/\/verify-otp$/);

    // A failed attempt must not leave the form stuck in its submitting state.
    await verify.click();
    await expect(page).toHaveURL(/\/login$/);
    expect(api.callsTo("POST", "/api/users/otp/verify")).toHaveLength(2);
  });

  test("resends a code for the entered email", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto("/verify-otp");

    await page.getByLabel("NUS Email").fill(" E0123456@U.NUS.EDU ");
    await page.getByRole("button", { name: /Resend code/ }).click();

    await expect(page.getByText("A new code was sent.")).toBeVisible();
    expect(api.lastCall("POST", "/api/users/otp/resend")?.body).toEqual({
      email: "e0123456@u.nus.edu",
    });
  });

  test("refuses to resend without an email", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto("/verify-otp");

    await page.getByRole("button", { name: /Resend code/ }).click();

    await expect(page.getByText("Enter your email first")).toBeVisible();
    expect(api.callsTo("POST", "/api/users/otp/resend")).toHaveLength(0);
  });

  test("reports a failed resend", async ({ page }) => {
    await mockApi(page, {
      "POST /api/users/otp/resend": () => ({
        status: 429,
        body: { code: "rate_limited", message: "Too many requests" },
      }),
    });
    await page.goto("/verify-otp");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByRole("button", { name: /Resend code/ }).click();

    await expect(page.getByText("Too many requests")).toBeVisible();
  });

  test("offers a way back to login", async ({ page }) => {
    await mockApi(page);
    await page.goto("/verify-otp");

    await page.getByRole("link", { name: "Back to login" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
