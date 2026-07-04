import { test, expect, type Page } from "@playwright/test";

const imageEvidence = {
  id: "ev-deeclip",
  case_id: "case-deeclip",
  filename: "questioned.jpg",
  original_filename: "questioned.jpg",
  file_size: 2048,
  file_type: "imagem",
  mime_type: "image/jpeg",
  sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
  uploaded_by: "1",
  created_at: "2026-06-20T00:00:00",
};

async function mockCommon(page: Page) {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "1",
        username: "perito",
        email: "perito@pf.gov.br",
        role: "perito",
        is_active: true,
      }),
    });
  });

  await page.route("**/api/v1/cases/case-deeclip", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-deeclip",
        protocol_number: "2026/DEECLIP",
        title: "Caso DeeCLIP",
        status: "aberto",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-deeclip/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([imageEvidence]),
    });
  });

  await page.route("**/api/v1/cases/case-deeclip/derivatives**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/evidences/ev-deeclip/file", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
        "base64",
      ),
    });
  });

  await page.route("**/api/v1/analysis/techniques**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "synthetic_image_detection",
          supported_types: ["imagem"],
          available: true,
          unavailable_reason: null,
        },
      ]),
    });
  });

  await page.route("**/api/v1/analysis", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "job-deeclip",
        status: "pending",
        progress: 5,
        progress_message: "Carregando modelos Detecção imagens sintéticas em CPU",
      }),
    });
  });

  await page.route("**/api/v1/analysis/job-deeclip", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "job-deeclip",
        status: "completed",
        progress: 100,
        progress_message: "Concluido",
      }),
    });
  });

  await page.route("**/api/v1/analysis/job-deeclip/result", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        inference_device: "cpu",
        individual_results: [
          ["DeeCLIP (CLIP ViT-L/14)", "0.7123", "0.2877", "-0.39", "AI", "CPU"],
        ],
      }),
    });
  });

  await page.route("**/api/v1/analysis/job-deeclip/result/file**", async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.addInitScript(() => {
    localStorage.setItem("va_access_token", "mock-token");
  });
}

test.describe("DeeCLIP synthetic image integration", () => {
  test("synthetic image workflow renders DeeCLIP result row", async ({ page }) => {
    await mockCommon(page);
    await page.goto("/cases/case-deeclip/analysis/synthetic_image_detection");

    await expect(page.getByRole("heading", { name: /Detecção de Imagens Sintéticas/i }).first()).toBeVisible();
    await expect(page.getByText(/DeeCLIP/i).first()).toBeVisible();

    await expect(page.getByRole("button", { name: /questioned\.jpg/i })).toBeVisible();
    await page.getByRole("button", { name: /Analisar Imagem/i }).click();

    await expect(page.getByText("DeeCLIP (CLIP ViT-L/14)")).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("0.7123")).toBeVisible();
    await expect(page.getByText("AI").first()).toBeVisible();
  });
});
