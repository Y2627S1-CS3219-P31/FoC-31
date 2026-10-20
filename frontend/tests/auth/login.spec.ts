// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): regression tests for
// the login screen. Reviewed by authors.
import { expect, test } from "@playwright/test";
import {
  CLIENT_PROFILE,
  fakeJwt,
  mockApi,
  storedToken,
} from "../support/api-mocks";

test.describe("login", () => {
  test("rejects invalid input without calling the API", async ({ page }) => {
    const api = await mockApi(page);
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("not-an-email");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(page.getByText("Enter a valid email")).toBeVisible();
    await expect(page.getByText("Password is required")).toBeVisible();
    expect(api.callsTo("POST", "/api/users/login")).toHaveLength(0);
    expect(await storedToken(page)).toBeNull();
  });

  test("logs in, persists the token and returns to the requested page", async ({
    page,
  }) => {
    const api = await mockApi(page);

    // Deep-linking to a protected page while signed out goes through /login.
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(page).toHaveURL(/\/profile$/);
    await expect(
      page.getByText(`Welcome back, ${CLIENT_PROFILE.display_name}`),
    ).toBeVisible();

    expect(api.lastCall("POST", "/api/users/login")?.body).toEqual({
      email: CLIENT_PROFILE.email,
      password: "Password1",
    });

    const token = await storedToken(page);
    expect(token).not.toBeNull();
    // The profile is fetched with the freshly issued bearer token.
    expect(api.lastCall("GET", "/api/users/me")?.authorization).toBe(
      `Bearer ${token}`,
    );

    // The session survives a full reload (token is persisted, not just state).
    await page.reload();
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.getByText("Client", { exact: true })).toBeVisible();
    expect(api.callsTo("POST", "/api/users/login")).toHaveLength(1);
  });

  test("disables the submit button while a login is in flight", async ({
    page,
  }) => {
    const api = await mockApi(page, {
      "POST /api/users/login": async () => {
        await new Promise((resolve) => setTimeout(resolve, 600));
        return {
          body: {
            access_token: fakeJwt(),
            token_type: "bearer",
            expires_in: 3600,
          },
        };
      },
    });
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("Password1");

    const submit = page.getByRole("button", { name: "Log In" });
    await submit.click();

    // Loading state blocks duplicate submissions until navigation completes.
    await expect(submit).toBeDisabled();
    await expect(page).toHaveURL(/\/suppliers$/);
    expect(api.callsTo("POST", "/api/users/login")).toHaveLength(1);
  });

  test("renders FastAPI-style validation details from the gateway", async ({
    page,
  }) => {
    await mockApi(page, {
      "POST /api/users/login": () => ({
        status: 422,
        body: {
          detail: [
            {
              loc: ["body", "email"],
              msg: "value is not a valid email address",
              type: "value_error",
            },
          ],
        },
      }),
    });
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(
      page.getByText("value is not a valid email address"),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("defaults to the supplier list when no return path is set", async ({
    page,
  }) => {
    await mockApi(page);
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(page).toHaveURL(/\/suppliers$/);
    await expect(
      page.getByText("No suppliers match your filters."),
    ).toBeVisible();
  });

  test("shows the gateway error and stays signed out on invalid credentials", async ({
    page,
  }) => {
    await mockApi(page, {
      "POST /api/users/login": () => ({
        status: 401,
        body: {
          code: "invalid_credentials",
          message: "Incorrect email or password",
        },
      }),
    });
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(page.getByText("Incorrect email or password")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    expect(await storedToken(page)).toBeNull();

    // Protected pages stay protected after a failed login.
    await page.goto("/suppliers");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("shows a generic message when the gateway is unreachable", async ({
    page,
  }) => {
    await mockApi(page, {
      "POST /api/users/login": () => ({ abort: true }),
    });
    await page.goto("/login");

    await page.getByLabel("NUS Email").fill("e0123456@u.nus.edu");
    await page.getByLabel("Password").fill("Password1");
    await page.getByRole("button", { name: "Log In" }).click();

    await expect(page.getByText("Login failed. Try again.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
    expect(await storedToken(page)).toBeNull();
  });

  test("switches to the registration tab", async ({ page }) => {
    await mockApi(page);
    await page.goto("/login");

    await page.getByRole("tab", { name: "Sign Up" }).click();
    await expect(page).toHaveURL(/\/register$/);
    await expect(
      page.getByRole("heading", { name: "Create your account" }),
    ).toBeVisible();
  });
});
