import { test, expect } from "@playwright/test";

async function mockAuthRoutes(page: any) {
  await page.route("**/api/v1/auth/login", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "mock-token",
        token_type: "bearer",
        user: {
          id: "1",
          username: "e2euser",
          email: "e2e@pf.gov.br",
          role: "perito",
          is_active: true,
        },
      }),
    });
  });

  await page.route("**/api/v1/auth/me", async (route: any) => {
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

  await page.route("**/api/v1/cases", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "case-1",
          protocol_number: "2024/001",
          title: "Caso Teste",
          description: "Descricao de teste",
          status: "aberto",
          created_by: "1",
          created_at: "2026-05-30T00:00:00",
          updated_at: "2026-05-30T00:00:00",
        },
      ]),
    });
  });
}

test.describe("Login", () => {
  test("successful login redirects to cases list", async ({ page }) => {
    await mockAuthRoutes(page);

    await page.goto("/login");
    await page.fill('input[id="username"]', "e2euser");
    await page.fill('input[id="password"]', "E2ESenha123!");
    await page.click('button[type="submit"]');

    await page.waitForURL("/");
    await expect(page.locator("h1")).toContainText("Casos");
  });

  test("invalid credentials show error", async ({ page }) => {
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Credenciais invalidas" }),
      });
    });

    await page.goto("/login");
    await page.fill('input[id="username"]', "e2euser");
    await page.fill('input[id="password"]', "wrongpassword");
    await page.click('button[type="submit"]');

    await expect(page.locator(".error-message")).toContainText("Credenciais invalidas");
  });
});
