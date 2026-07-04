import { test, expect, type Page } from "@playwright/test";

const imageEvidence = {
  id: "ev-questioned",
  case_id: "case-miml",
  filename: "questioned.jpg",
  original_filename: "questioned.jpg",
  file_size: 2048,
  file_type: "imagem",
  mime_type: "image/jpeg",
  sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
  uploaded_by: "1",
  created_at: "2026-06-17T00:00:00",
};

async function mockCommon(page: Page, role: "admin" | "perito") {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "1",
        username: role,
        email: `${role}@pf.gov.br`,
        role,
        is_active: true,
      }),
    });
  });

  await page.route("**/api/v1/cases/case-miml", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-miml",
        protocol_number: "2026/MIML",
        title: "Caso MIML",
        status: "aberto",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-miml/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([imageEvidence]),
    });
  });

  await page.route("**/api/v1/cases/case-miml/derivatives**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/analysis/imdlbenco/methods", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "miml_apscnet",
          name: "MIML APSC-Net",
          venue: "MIML",
          tier: "ecosystem",
          description: "APSC-Net oficial MIML",
          repo_url: "https://github.com/qcf-568/MIML/tree/main/models%20for%20IML",
          status: "weights_missing",
          ready: false,
          unavailable_reason: "Dependencias APSC-Net ausentes: instale mmcv/mmseg.",
          variants: null,
        },
      ]),
    });
  });

  await page.addInitScript(() => {
    localStorage.setItem("va_access_token", "mock-token");
  });
}

test.describe("MIML APSC-Net availability", () => {
  test("admin sees MIML APSC-Net method", async ({ page }) => {
    await mockCommon(page, "admin");

    await page.goto("/cases/case-miml/analysis/image-group/dl-manipulacao?tab=miml_apscnet");

    await expect(page.getByRole("tab", { name: /MIML APSC-Net/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /MIML APSC-Net/i })).toHaveAttribute("aria-selected", "true");
  });

  test("perito also sees MIML APSC-Net method", async ({ page }) => {
    await mockCommon(page, "perito");

    await page.goto("/cases/case-miml/analysis/image-group/dl-manipulacao");

    await expect(page.getByRole("tab", { name: /MIML APSC-Net/i })).toBeVisible();
  });
});
