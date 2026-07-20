import { test, expect, type Page } from "@playwright/test";

const audioEvidence = {
  id: "ev-audio-lr",
  case_id: "case-audio-lr",
  filename: "questioned.wav",
  original_filename: "questioned.wav",
  file_size: 4096,
  file_type: "audio",
  mime_type: "audio/wav",
  sha256: "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1",
  uploaded_by: "1",
  created_at: "2026-06-21T00:00:00",
};

const referenceCatalog = {
  categories: [
    {
      id: "commercial_clone",
      label: "Clonagem comercial",
      bases: [
        {
          id: "SONAR",
          label: "SONAR",
          generators: [{ subgroup: "xTTS", label: "xTTS", count: 100 }],
        },
      ],
    },
  ],
  detector_eer_labels: ["DF Arena 1B", "SLS XLS-R", "WeDefense"],
  default_reference_items: [{ base_group: "SONAR", subgroup: "xTTS" }],
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

  await page.route("**/api/v1/cases/case-audio-lr", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-audio-lr",
        protocol_number: "2026/AUDIO",
        title: "Caso Audio LR",
        status: "aberto",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-audio-lr/evidences**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([audioEvidence]),
    });
  });

  await page.route("**/api/v1/cases/case-audio-lr/derivatives**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/cases/case-audio-lr/audio-metadata**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route("**/api/v1/evidences/ev-audio-lr/file", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/wav",
      body: Buffer.alloc(128),
    });
  });

  await page.route("**/api/v1/analysis/techniques**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "audio_spoofing_detection",
          supported_types: ["audio"],
          available: true,
          unavailable_reason: null,
        },
      ]),
    });
  });

  await page.route("**/api/v1/analysis/audio-spoofing-detectors**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { id: "df_arena_1b", label: "DF Arena 1B", available: true },
        { id: "sls_xlsr", label: "SLS XLS-R (ACM MM 2024)", available: true },
        { id: "wedefense_wavlm_mhfa", label: "WeDefense ASV2025 WavLM + MHFA", available: true },
      ]),
    });
  });

  await page.route("**/api/v1/analysis/audio-spoofing-reference-catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(referenceCatalog),
    });
  });

  await page.addInitScript(() => {
    localStorage.setItem("va_access_token", "mock-token");
    localStorage.setItem("va_file_list_view_mode", "list");
  });
}

async function selectAudioEvidence(page: Page) {
  await expect(page.getByText("questioned.wav")).toBeVisible({ timeout: 10000 });
  await page.getByText("questioned.wav").click();
}

function lrResultWithTypicality() {
  return {
    success: true,
    inference_device: "cpu",
    selected_analyses: ["df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"],
    individual_results: [
      ["DF Arena 1B", "0.30", "0.70", "0.85", "Bonafide", "cpu"],
      ["SLS XLS-R (ACM MM 2024)", "0.40", "0.60", "0.41", "Incerto", "cpu"],
      ["WeDefense ASV2025 WavLM + MHFA", "0.35", "0.65", "0.62", "Incerto", "cpu"],
    ],
    reference_lr: {
      latent_typicality: true,
      used_cache: true,
      typicality_config: { system: "D", distance: "cosine", k: 5 },
      selected_count: 1,
      sample_rows: 6,
      meta_classifier: "logistic",
      meta_classifier_label: "Regressao Logistica",
      questioned: { log10_lr: 0.12, lr: 1.32 },
      test_metrics: { cllr: 0.45, min_cllr: 0.4, eer: 0.08 },
      artifact_filenames: {
        tippett: "lr_reference_tippett.png",
        distribution: "lr_reference_distribution.png",
        identity: "lr_reference_identity.png",
        summary: "lr_reference_summary.txt",
      },
      note: "LR > 1 favorece H1=bonafide/autentico.",
    },
  };
}

test.describe("audio spoofing LR typicality UI", () => {
  test("checkbox tipicidade visivel e desligado por padrao", async ({ page }) => {
    await mockCommon(page);
    await page.goto("/cases/case-audio-lr/analysis/audio_spoofing");
    const checkbox = page.getByLabel("Tipicidade latente (k-NN)");
    await expect(checkbox).toBeVisible();
    await expect(checkbox).not.toBeChecked();
  });

  test("envia use_latent_typicality ao marcar checkbox", async ({ page }) => {
    await mockCommon(page);

    let postBody: { parameters?: Record<string, unknown> } | undefined;
    await page.route("**/api/v1/analysis", async (route) => {
      postBody = route.request().postDataJSON() as { parameters?: Record<string, unknown> };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-audio-lr",
          status: "pending",
          progress: 5,
          progress_message: "Iniciando",
        }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "job-audio-lr",
          status: "completed",
          progress: 100,
          progress_message: "Concluido",
        }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr/result", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, inference_device: "cpu", individual_results: [] }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr/result/file**", async (route) => {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    });

    await page.goto("/cases/case-audio-lr/analysis/audio_spoofing");
    await selectAudioEvidence(page);
    await page.getByLabel("Tipicidade latente (k-NN)").check();
    await page.getByRole("button", { name: /analisar audio/i }).click();

    await expect.poll(() => postBody?.parameters?.use_latent_typicality).toBe(true);
    expect(postBody?.parameters?.use_augmented_reference).toBe(false);
    expect(postBody?.parameters?.meta_classifier).toBe("logistic");
    expect(postBody?.parameters?.selected_analyses).toEqual([
      "df_arena_1b",
      "sls_xlsr",
      "wedefense_wavlm_mhfa",
    ]);
  });

  test("painel LR exibe badge de tipicidade latente", async ({ page }) => {
    await mockCommon(page);

    await page.route("**/api/v1/analysis", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-audio-lr-typ",
          status: "pending",
          progress: 5,
          progress_message: "Iniciando",
        }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr-typ", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "job-audio-lr-typ",
          status: "completed",
          progress: 100,
          progress_message: "Concluido",
        }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr-typ/result", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(lrResultWithTypicality()),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-lr-typ/result/file**", async (route) => {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    });

    await page.goto("/cases/case-audio-lr/analysis/audio_spoofing");
    await selectAudioEvidence(page);
    await page.getByRole("button", { name: /analisar audio/i }).click();

    await expect(page.getByText(/Tipicidade latente \(k-NN\): sistema D/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByText(/Cache de calibração reutilizado/i)).toBeVisible();
  });

  test("regressao: use_augmented_reference ainda enviado no payload", async ({ page }) => {
    await mockCommon(page);

    let postBody: { parameters?: Record<string, unknown> } | undefined;
    await page.route("**/api/v1/analysis", async (route) => {
      postBody = route.request().postDataJSON() as { parameters?: Record<string, unknown> };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-audio-aug",
          status: "pending",
          progress: 5,
          progress_message: "Iniciando",
        }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-aug", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "job-audio-aug", status: "completed", progress: 100 }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-aug/result", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, individual_results: [] }),
      });
    });

    await page.route("**/api/v1/analysis/job-audio-aug/result/file**", async (route) => {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    });

    await page.goto("/cases/case-audio-lr/analysis/audio_spoofing");
    await selectAudioEvidence(page);
    await page.getByLabel(/DF Arena 1B/i).uncheck();
    await page.getByLabel(/Usar população de referência aumentada/i).check();
    await page.getByRole("button", { name: /analisar audio/i }).click();

    await expect.poll(() => postBody?.parameters?.use_augmented_reference).toBe(true);
    expect(postBody?.parameters?.selected_analyses).toEqual(["sls_xlsr", "wedefense_wavlm_mhfa"]);
  });
});
