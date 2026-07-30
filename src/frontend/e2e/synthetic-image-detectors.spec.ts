import { test, expect, type Page } from "@playwright/test";

/** Catálogo canônico alinhado a forensics/synthetic_image_detection/runtime.py */
const DETECTOR_CATALOG = [
  {
    id: "ai_image_detector_deploy",
    label: "ai-image-detector-deploy",
    available: true,
    unavailable_reason: null,
  },
  {
    id: "sdxl_flux_detector_v1_1",
    label: "sdxl-flux-detector v1.1",
    available: true,
    unavailable_reason: null,
  },
  {
    id: "bfree",
    label: "B-Free / Bias-free",
    available: true,
    unavailable_reason: null,
  },
  {
    id: "corvi2023",
    label: "DMImageDetection (Corvi2023)",
    available: true,
    unavailable_reason: null,
  },
  {
    id: "safe",
    label: "SAFE (KDD 2025)",
    available: true,
    unavailable_reason: null,
  },
];

const imageEvidence = {
  id: "ev-synthetic",
  case_id: "case-synthetic",
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
  await page.addInitScript(() => {
    localStorage.setItem("va_access_token", "mock-token");
    localStorage.setItem("va_refresh_token", "mock-refresh");
  });

  // Registrado primeiro (menor prioridade): evita 401 do backend real.
  await page.route("**/api/v1/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: route.request().method() === "GET" ? "[]" : "{}",
    });
  });

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

  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "mock-token",
        refresh_token: "mock-refresh",
        expires_in: 900,
      }),
    });
  });

  await page.route("**/api/v1/cases/case-synthetic", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-synthetic",
        protocol_number: "2026/SYN",
        title: "Caso Imagens Sinteticas",
        status: "aberto",
        storage_mode: "va",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-synthetic/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([imageEvidence]),
    });
  });

  await page.route("**/api/v1/cases/case-synthetic/derivatives**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/cases/case-synthetic/references**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ groups: [] }),
    });
  });

  await page.route("**/api/v1/cases/case-synthetic/closure-status**", async (route) => {
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

  await page.route("**/api/v1/evidences/ev-synthetic/file", async (route) => {
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

  await page.route("**/api/v1/analysis/synthetic-image-detectors**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(DETECTOR_CATALOG),
    });
  });

  await page.route("**/api/v1/analysis/synthetic-reference-catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        categories: [
          {
            id: "diffusion_cnn_modern",
            label: "Difusão moderna",
            description: "População de teste E2E",
            bases: [
              {
                id: "e2e_base",
                label: "Base E2E",
                generators: [{ id: "gen_a", label: "Gerador A" }],
              },
            ],
          },
        ],
        default_reference_items: [{ base_group: "e2e_base", subgroup: "gen_a" }],
      }),
    });
  });

}

test.describe("synthetic image detection — catalogo atual", () => {
  test("exibe os cinco detectores canonicos e oculta os aposentados", async ({ page }) => {
    await mockCommon(page);

    await page.goto("/cases/case-synthetic/analysis/synthetic_image_detection");
    await expect(page.getByRole("heading", { name: /Detecção de Imagens Sintéticas/i }).first()).toBeVisible({
      timeout: 15000,
    });

    for (const detector of DETECTOR_CATALOG) {
      await expect(page.getByText(detector.label, { exact: true }).first()).toBeVisible();
    }

    await expect(page.getByText(/CLIDE/i)).toHaveCount(0);
    await expect(page.getByText(/DeeCLIP/i)).toHaveCount(0);
    await expect(page.getByText(/UniversalFakeDetect/i)).toHaveCount(0);
    await expect(page.getByText(/^FSD$/i)).toHaveCount(0);

    await page.getByRole("button", { name: /Limpar/i }).click();
    await page.getByLabel(/B-Free \/ Bias-free/i).check();
    await page.getByLabel(/SAFE \(KDD 2025\)/i).check();
    await expect(page.getByLabel(/B-Free \/ Bias-free/i)).toBeChecked();
    await expect(page.getByLabel(/SAFE \(KDD 2025\)/i)).toBeChecked();
    await expect(page.getByLabel(/ai-image-detector-deploy/i)).not.toBeChecked();
  });
});
