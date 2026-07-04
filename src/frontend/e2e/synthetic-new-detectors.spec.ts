import { test, expect, type Page } from "@playwright/test";

const imageEvidence = {
  id: "ev-new-detectors",
  case_id: "case-new-detectors",
  filename: "questioned.jpg",
  original_filename: "questioned.jpg",
  file_size: 2048,
  file_type: "imagem",
  mime_type: "image/jpeg",
  sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
  uploaded_by: "1",
  created_at: "2026-06-21T00:00:00",
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

  await page.route("**/api/v1/cases/case-new-detectors", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-new-detectors",
        protocol_number: "2026/NEW",
        title: "Caso Novos Detectores",
        status: "aberto",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-new-detectors/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([imageEvidence]),
    });
  });

  await page.route("**/api/v1/cases/case-new-detectors/derivatives**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/evidences/ev-new-detectors/file", async (route) => {
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

  await page.route("**/api/v1/analysis/job-new-detectors", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "job-new-detectors",
        status: "completed",
        progress: 100,
        progress_message: "Concluido",
      }),
    });
  });

  await page.route("**/api/v1/analysis/job-new-detectors/result", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        inference_device: "cpu",
        selected_analyses: ["fsd", "universal_fake_detect", "truebees_clip_d"],
        individual_results: [
          ["FSD (CVPR 2025)", "-2.5000", "N/A", "limiar=-2.00", "AI", "CPU"],
          ["UniversalFakeDetect (CLIP ViT-L/14)", "0.8000", "0.2000", "-0.60", "AI", "CPU"],
          ["GRIP CLIP-D (clipdet_latent10k_plus)", "0.2000", "0.8000", "LLR=-1.3863", "REAL", "CPU"],
        ],
      }),
    });
  });

  await page.route("**/api/v1/analysis/job-new-detectors/result/file**", async (route) => {
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.addInitScript(() => {
    localStorage.setItem("va_access_token", "mock-token");
  });
}

test.describe("new synthetic image detectors integration", () => {
  test("sends selected FSD, UFD and CLIP-D analyses and renders result rows", async ({ page }) => {
    await mockCommon(page);

    let selectedAnalyses: string[] | undefined;
    await page.route("**/api/v1/analysis", async (route) => {
      const body = route.request().postDataJSON() as { parameters?: { selected_analyses?: string[] } };
      selectedAnalyses = body.parameters?.selected_analyses;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-new-detectors",
          status: "pending",
          progress: 5,
          progress_message: "Carregando modelos Detecção imagens sintéticas em CPU",
        }),
      });
    });

    await page.goto("/cases/case-new-detectors/analysis/synthetic_image_detection");

    await expect(page.getByText("FSD").first()).toBeVisible();
    await expect(page.getByText("UniversalFakeDetect").first()).toBeVisible();
    await expect(page.getByText("GRIP CLIP-D (10k+)").first()).toBeVisible();

    await page.getByRole("button", { name: /Limpar/i }).click();
    await page.getByLabel(/FSD/i).check();
    await page.getByLabel(/UniversalFakeDetect/i).check();
    await page.getByLabel(/GRIP CLIP-D/i).check();
    await page.getByRole("button", { name: /Analisar Imagem/i }).click();

    await expect.poll(() => selectedAnalyses).toEqual([
      "fsd",
      "universal_fake_detect",
      "truebees_clip_d",
    ]);
    await expect(page.getByRole("cell", { name: "FSD (CVPR 2025)" })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("cell", { name: "UniversalFakeDetect (CLIP ViT-L/14)" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "GRIP CLIP-D (clipdet_latent10k_plus)" })).toBeVisible();
  });
});

