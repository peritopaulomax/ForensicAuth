import { test, expect } from "@playwright/test";

test.describe("Audio spoofing multi-detector UI", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Usuario").fill("admin");
    await page.getByLabel("Senha").fill("admin123");
    await page.getByRole("button", { name: /entrar/i }).click();
    await page.waitForURL("**/dashboard");
  });

  test("hub exibe selecao de detectores e tabela de escores", async ({ page }) => {
    await page.goto("/cases");
    const firstCase = page.locator("table tbody tr").first();
    await expect(firstCase).toBeVisible();
    await firstCase.click();

    await page.getByRole("link", { name: /spoofing/i }).first().click();
    await expect(page.getByText("Detectores de spoofing")).toBeVisible();
    await expect(page.getByLabel(/DF Arena 1B/i)).toBeVisible();
    await expect(page.getByLabel(/SLS XLS-R/i)).toBeVisible();
    await expect(page.getByLabel(/WeDefense ASV2025/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /analisar audio/i })).toBeVisible();
  });
});
