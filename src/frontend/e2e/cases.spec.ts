import { test, expect } from "@playwright/test";

async function mockAuth(page: any) {
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
}

test.describe("Cases", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page);

    await page.route("**/api/v1/cases", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "case-1",
            protocol_number: "2024/001",
            inquiry_number: "12345/2024",
            process_number: "0001234-12.2024.8.26.0100",
            title: "Caso Teste E2E",
            description: "Descricao do caso de teste",
            status: "aberto",
            created_by: "1",
            created_at: "2026-05-30T00:00:00",
            updated_at: "2026-05-30T00:00:00",
          },
        ]),
      });
    });

    await page.goto("/login");
    await page.fill('input[id="username"]', "e2euser");
    await page.fill('input[id="password"]', "E2ESenha123!");
    await page.click('button[type="submit"]');
    await page.waitForURL("/");
  });

  test("displays cases list", async ({ page }) => {
    await expect(page.locator("h1")).toContainText("Casos");
    await expect(page.locator("text=Caso Teste E2E")).toBeVisible();
    await expect(page.locator("text=Protocolo: 2024/001")).toBeVisible();
  });

  test("navigation to new case form works", async ({ page }) => {
    await page.click('text=+ Novo Caso');
    await page.waitForURL("/cases/new");
    await expect(page.locator("h1")).toContainText("Novo Caso");
  });

  test("clicking a case navigates to case detail", async ({ page }) => {
    await page.route("**/api/v1/cases/case-1", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "case-1",
          protocol_number: "2024/001",
          inquiry_number: "12345/2024",
          process_number: "0001234-12.2024.8.26.0100",
          title: "Caso Teste E2E",
          description: "Descricao do caso de teste",
          status: "aberto",
          created_by: "1",
          created_at: "2026-05-30T00:00:00",
          updated_at: "2026-05-30T00:00:00",
        }),
      });
    });

    await page.route("**/api/v1/cases/case-1/evidences", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.click('text=Caso Teste E2E');
    await page.waitForURL("/cases/case-1");
    await expect(page.locator("h1")).toContainText("Caso Teste E2E");
  });

  test("case detail has analysis tab", async ({ page }) => {
    await page.route("**/api/v1/cases/case-1", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "case-1",
          protocol_number: "2024/001",
          inquiry_number: "12345/2024",
          process_number: "0001234-12.2024.8.26.0100",
          title: "Caso Teste E2E",
          description: "Descricao do caso de teste",
          status: "aberto",
          created_by: "1",
          created_at: "2026-05-30T00:00:00",
          updated_at: "2026-05-30T00:00:00",
        }),
      });
    });

    await page.route("**/api/v1/cases/case-1/evidences", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "ev-1",
            case_id: "case-1",
            filename: "foto.jpg",
            original_filename: "foto.jpg",
            file_size: 2048,
            file_type: "imagem",
            mime_type: "image/jpeg",
            sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
            uploaded_by: "1",
            created_at: "2026-05-30T00:00:00",
          },
        ]),
      });
    });

    await page.route("**/api/v1/analysis/techniques", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ name: "ela", supported_types: ["imagem"] }]),
      });
    });

    await page.click('text=Caso Teste E2E');
    await page.waitForURL("/cases/case-1");
    await expect(page.locator("h1")).toContainText("Caso Teste E2E");

    await page.click('[data-testid="tab-analises"]');
    await expect(page.locator("text=Técnicas disponíveis")).toBeVisible();
    await expect(page.locator("text=Error Level Analysis (ELA)")).toBeVisible();
  });
});
