// AI-assisted (GitHub Copilot Chat, DeepSeek V4.1 Flash): warms the Vite dev
// server once before the suite runs so first-visit dependency pre-bundling
// cannot force page reloads in the middle of a regression test.
// Reviewed by authors.
import { chromium, type FullConfig } from "@playwright/test";

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use?.baseURL ?? "http://localhost:5173";
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    // Vite optimizes dependencies on the first request and reloads the page
    // while doing so; retry until the app renders in a stable state.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page
        .goto(`${baseURL}/login`, {
          waitUntil: "domcontentloaded",
          timeout: 60_000,
        })
        .catch(() => undefined);

      try {
        await page
          .getByRole("heading", { name: "Welcome back" })
          .waitFor({ timeout: 15_000 });
        return;
      } catch {
        // Reloaded by the optimizer — try again.
      }
    }

    throw new Error("Vite dev server did not render the login page");
  } finally {
    await browser.close();
  }
}
