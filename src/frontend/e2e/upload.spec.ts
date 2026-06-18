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

test.describe("Upload", () => {
  test("upload evidence in case detail", async ({ page }) => {
    await mockAuth(page);

    await page.route("**/api/v1/cases", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "case-1",
            protocol_number: "2024/001",
            title: "Caso Upload Test",
            description: "",
            status: "aberto",
            created_by: "1",
            created_at: "2026-05-30T00:00:00",
            updated_at: "2026-05-30T00:00:00",
          },
        ]),
      });
    });

    await page.route("**/api/v1/cases/case-1", async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "case-1",
          protocol_number: "2024/001",
          title: "Caso Upload Test",
          description: "",
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

    await page.route("**/api/v1/evidences/upload", async (route: any) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "evidence-123",
          case_id: "case-1",
          filename: "test.jpg",
          original_filename: "test.jpg",
          file_size: 1024,
          file_type: "imagem",
          mime_type: "image/jpeg",
          sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
          uploaded_by: "1",
          created_at: "2026-05-30T00:00:00",
        }),
      });
    });

    await page.goto("/login");
    await page.fill('input[id="username"]', "e2euser");
    await page.fill('input[id="password"]', "E2ESenha123!");
    await page.click('button[type="submit"]');
    await page.waitForURL("/");

    await page.click('text=Caso Upload Test');
    await page.waitForURL("/cases/case-1");
    await expect(page.locator("h1")).toContainText("Caso Upload Test");

    const buffer = Buffer.from("\xff\xd8\xff\xe0\x00\x10JFIF");
    await page.setInputFiles('input[type="file"]', {
      name: "test.jpg",
      mimeType: "image/jpeg",
      buffer,
    });

    await expect(page.locator("text=test.jpg")).toBeVisible();
    await expect(page.locator("text=1 KB")).toBeVisible();
  });
});
