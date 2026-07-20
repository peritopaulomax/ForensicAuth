import { test, expect } from "@playwright/test";

async function mockAuth(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "1",
        username: "e2eadmin",
        email: "e2e@pf.gov.br",
        role: "admin",
        is_active: true,
      }),
    });
  });
}

async function mockCaseData(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/cases/case-pad", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-pad",
        protocol_number: "2026/PAD",
        inquiry_number: "",
        process_number: "",
        title: "Caso PAD",
        description: "Caso de teste PAD",
        status: "aberto",
        storage_mode: "va",
        created_by: "1",
        created_at: "2026-06-22T00:00:00Z",
        updated_at: "2026-06-22T00:00:00Z",
        evidence_count: 1,
      }),
    });
  });

  await page.route("**/api/v1/cases/case-pad/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "ev-pad",
          case_id: "case-pad",
          filename: "face.jpg",
          original_filename: "face.jpg",
          file_path: "/uploads/ev-pad.jpg",
          file_size: 12345,
          file_type: "imagem",
          mime_type: "image/jpeg",
          sha256: "a".repeat(64),
          uploaded_by: "1",
          extra_metadata: {},
          created_at: "2026-06-22T00:00:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/v1/cases/case-pad/derivatives", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/cases/case-pad/references", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ groups: [] }),
    });
  });

  await page.route("**/api/v1/cases/case-pad/closure-status", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        current_user_must_sign: false,
        required_signers: [],
        pending_signers: [],
        pending_count: 0,
        fully_closed: false,
        closure_pending: false,
        message: "",
      }),
    });
  });
}

test.describe("PAD navigation", () => {
  test("card click opens PAD analysis page", async ({ page }) => {
    await mockAuth(page);
    await mockCaseData(page);

    await page.route("**/api/v1/analysis/techniques**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            name: "presentation_attack_detection",
            supported_types: ["imagem"],
            available: true,
            unavailable_reason: null,
          },
          {
            name: "moe_ffd",
            supported_types: ["imagem"],
            available: true,
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
      localStorage.setItem("va_access_token", "mock-token");
    });

    await page.goto("/cases/case-pad?tab=analises&media=imagem");

    const card = page.getByRole("heading", { name: /Deep Learning: Manipulação e Spoofing Facial/i });
    await expect(card).toBeVisible({ timeout: 15000 });
    await card.click();

    await page.waitForURL("**/cases/case-pad/analysis/image-group/dl-facial-spoofing**", { timeout: 10000 });
    await expect(
      page.getByRole("heading", { name: /Deep Learning: Manipulação e Spoofing Facial/i }).first(),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: /Detecção de Ataques de Apresentação/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Analisar imagem/i })).toBeVisible();
  });
});
