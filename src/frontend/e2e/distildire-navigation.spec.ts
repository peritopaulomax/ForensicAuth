import { test, expect } from "@playwright/test";

async function mockAuth(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "1",
        username: "e2euser",
        email: "e2e@pf.gov.br",
        role: "perito",
        is_active: true,
      }),
    });
  });
}

test.describe("DistilDIRE navigation", () => {
  test("card click opens dedicated analysis page", async ({ page }) => {
    await mockAuth(page);

    await page.route("**/api/v1/cases/case-dd", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "case-dd",
          protocol_number: "2026/DD",
          title: "Caso DistilDIRE",
          status: "aberto",
        }),
      });
    });

    await page.route("**/api/v1/cases/case-dd/evidences**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });

    await page.route("**/api/v1/analysis/techniques**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            name: "distildire",
            supported_types: ["imagem"],
            available: true,
            unavailable_reason: null,
          },
          {
            name: "synthetic_image_detection",
            supported_types: ["imagem"],
            available: true,
          },
        ]),
      });
    });

    await page.route("**/api/v1/imdl/methods**", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });

    await page.addInitScript(() => {
      localStorage.setItem(
        "auth",
        JSON.stringify({ token: "mock-token", user: { id: "1", role: "perito" } })
      );
    });

    await page.goto("/cases/case-dd?tab=analises&media=imagem");

    const card = page.getByRole("heading", { name: /DistilDIRE/i });
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.click();

    await page.waitForURL("**/cases/case-dd/analysis/distildire", { timeout: 10000 });
    await expect(page.getByRole("heading", { name: /DistilDIRE/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Analisar imagem/i })).toBeVisible();
  });
});
