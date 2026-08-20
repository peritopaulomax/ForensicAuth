import { test, expect, type Page } from "@playwright/test";

const CASE_ID = "case-del";

async function mockCaseShell(page: Page) {
  // Registrado primeiro: rotas especificas abaixo tem precedencia (Playwright usa a ultima).
  // Sem isso, um 401 de endpoint nao mockado dispara logout e redireciona para /login.
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("audio-metadata")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
      return;
    }
    if (url.includes("/custody")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ records: [], total: 0 }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "mock-token",
        refresh_token: "mock-refresh",
        token_type: "bearer",
        expires_in: 900,
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

  await page.route("**/api/v1/auth/me", async (route) => {
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

  const caseBody = {
    id: CASE_ID,
    protocol_number: "2026/DEL",
    title: "Caso Exclusao",
    description: "",
    status: "aberto",
    created_by: "1",
    created_at: "2026-05-30T00:00:00",
    updated_at: "2026-05-30T00:00:00",
  };

  await page.route("**/api/v1/cases", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([caseBody]),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(caseBody),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/closure-status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        case_status: "aberto",
        fully_closed: false,
        closure_pending: false,
        active_closure_id: null,
        required_signers: [],
        pending_signers: [],
        pending_count: 0,
        all_signed: false,
        current_user_must_sign: false,
        current_user_can_initiate: true,
        message: "Caso aberto",
      }),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/derivatives`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/references**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ groups: [], global_groups: [] }),
    });
  });

  await page.route("**/api/v1/audit/verify-case-forensic/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        valid: true,
        chain: { valid: true, records_checked: 0, first_invalid: null },
        signatures: { checked: 0, invalid: [] },
        files: { checked: 0, missing: [], hash_mismatch: [] },
        provenance: { issues: [] },
        closures: [],
        warnings: [],
        generated_at: "2026-01-01T00:00:00Z",
      }),
    });
  });

  await page.route("**/api/v1/evidences/*/thumbnail", async (route) => {
    await route.fulfill({ status: 404, body: "no" });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/evidences`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "ev-1",
          case_id: CASE_ID,
          filename: "q.jpg",
          original_filename: "questionado.jpg",
          file_size: 1000,
          file_type: "imagem",
          mime_type: "image/jpeg",
          sha256: "a".repeat(64),
          extra_metadata: { questioned_group_label: "Lote A" },
          uploaded_by: "1",
          created_at: "2026-01-01T00:00:00",
          group_label: "Lote A",
        },
      ]),
    });
  });
}

async function openCase(page: Page) {
  await page.goto("/login");
  await page.fill('input[id="username"]', "e2euser");
  await page.fill('input[id="password"]', "E2ESenha123!");
  await page.click('button[type="submit"]');
  await page.waitForURL("/");
  await page.click("text=Caso Exclusao");
  await page.waitForURL(`/cases/${CASE_ID}`);
  await expect(page.getByText("questionado.jpg").first()).toBeVisible({ timeout: 10000 });
}

test("modal de exclusao mostra dependentes e permite cascade", async ({ page }) => {
  await mockCaseShell(page);

  await page.route(`**/api/v1/cases/${CASE_ID}/evidences/deletion-preview`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        case_id: CASE_ID,
        targets: [
          {
            evidence_id: "ev-1",
            original_filename: "questionado.jpg",
            file_type: "imagem",
            is_derived: false,
            technique: null,
            artifact_role: null,
            derivation_group_id: "ev-1",
          },
        ],
        dependents: [
          {
            evidence_id: "der-1",
            original_filename: "ela_q.png",
            file_type: "imagem",
            is_derived: true,
            technique: "ela",
            artifact_role: "ela_visual",
            derivation_group_id: "job-1",
            exclusive: true,
            parents: [
              {
                evidence_id: "ev-1",
                role: "questioned",
                original_filename: "questionado.jpg",
                in_scope: true,
              },
            ],
            retained_parents: [],
          },
          {
            evidence_id: "der-2",
            original_filename: "prnu.html",
            file_type: "outros",
            is_derived: true,
            technique: "prnu",
            artifact_role: "prnu_correlation_surface",
            derivation_group_id: "job-2",
            exclusive: false,
            parents: [],
            retained_parents: ["fingerprint_d70.npy"],
          },
        ],
        dependent_count: 2,
        cascade_count: 1,
        retained_count: 1,
        package_count: 1,
      }),
    });
  });

  let deleteBody: Record<string, unknown> = {};
  await page.route(`**/api/v1/cases/${CASE_ID}/evidences/delete`, async (route) => {
    deleteBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        deleted: ["ev-1"],
        dependents_deleted: ["der-1"],
        retained_dependents: [],
        failed: [],
      }),
    });
  });

  await openCase(page);
  await page.getByTitle("Excluir").first().click();

  const modal = page.getByTestId("confirm-delete-modal");
  await expect(modal).toBeVisible();
  await expect(modal.getByTestId("dependents-summary")).toContainText("2");
  await expect(modal).toContainText("questionado.jpg");
  await expect(modal).toContainText("fingerprint_d70.npy");

  await modal.getByTestId("scope-with-dependents").check();
  await expect(modal).toContainText("ela_q.png");
  await modal.getByTestId("confirm-delete").click();

  await expect(modal).toBeHidden();
  expect(deleteBody.include_dependent_derivatives).toBe(true);
  expect(deleteBody.evidence_ids).toEqual(["ev-1"]);
  await expect(page.getByText("questionado.jpg")).toHaveCount(0);
});

test("preview em 404 bloqueia exclusao mas oferece nova tentativa", async ({ page }) => {
  await mockCaseShell(page);

  let previewCalls = 0;
  await page.route(`**/api/v1/cases/${CASE_ID}/evidences/deletion-preview`, async (route) => {
    previewCalls += 1;
    if (previewCalls === 1) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not Found" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        case_id: CASE_ID,
        targets: [
          {
            evidence_id: "ev-1",
            original_filename: "questionado.jpg",
            file_type: "imagem",
            is_derived: false,
            technique: null,
            artifact_role: null,
            derivation_group_id: "ev-1",
          },
        ],
        dependents: [],
        dependent_count: 0,
        cascade_count: 0,
        retained_count: 0,
        package_count: 0,
      }),
    });
  });

  await openCase(page);
  await page.getByTitle("Excluir").first().click();

  const modal = page.getByTestId("confirm-delete-modal");
  await expect(modal.getByTestId("preview-failed")).toBeVisible();
  await expect(modal.getByTestId("confirm-delete")).toBeDisabled();

  await modal.getByTestId("retry-preview").click();

  await expect(modal.getByTestId("no-dependents")).toBeVisible();
  await expect(modal.getByTestId("preview-failed")).toBeHidden();
  await expect(modal.getByTestId("confirm-delete")).toBeEnabled();
});

test("falha parcial mantem item na lista e mostra erro", async ({ page }) => {
  await mockCaseShell(page);

  await page.route(`**/api/v1/cases/${CASE_ID}/evidences/deletion-preview`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        case_id: CASE_ID,
        targets: [
          {
            evidence_id: "ev-1",
            original_filename: "questionado.jpg",
            file_type: "imagem",
            is_derived: false,
            technique: null,
            artifact_role: null,
            derivation_group_id: "ev-1",
          },
        ],
        dependents: [],
        dependent_count: 0,
        cascade_count: 0,
        retained_count: 0,
        package_count: 0,
      }),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/evidences/delete`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        deleted: [],
        dependents_deleted: [],
        retained_dependents: [],
        failed: [{ evidence_id: "ev-1", detail: "Evidencia nao encontrada" }],
      }),
    });
  });

  await openCase(page);
  await page.getByTitle("Excluir").first().click();

  const modal = page.getByTestId("confirm-delete-modal");
  await expect(modal.getByTestId("no-dependents")).toBeVisible();
  await modal.getByTestId("confirm-delete").click();

  await expect(modal).toContainText("Evidencia nao encontrada");
  await modal.getByText("Cancelar").click();
  await expect(page.getByText("questionado.jpg").first()).toBeVisible();
});
