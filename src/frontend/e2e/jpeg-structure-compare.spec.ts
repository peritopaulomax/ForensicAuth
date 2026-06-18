import { test, expect, type Page } from "@playwright/test";

const CASE_ID = "f546da7f-e634-4742-8f16-610619a810d0";

const JPEG_EVIDENCES = [
  {
    id: "ev-jpeg-a",
    case_id: CASE_ID,
    filename: "7.jpg",
    original_filename: "7.jpg",
    file_size: 204800,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: "a".repeat(64),
    uploaded_by: "9a6920ec-2d1f-44d4-a4dc6cfe9b88944b",
    created_at: "2026-06-09T00:00:00",
  },
  {
    id: "ev-jpeg-b",
    case_id: CASE_ID,
    filename: "27.jpg",
    original_filename: "27.jpg",
    file_size: 198000,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: "b".repeat(64),
    uploaded_by: "9a6920ec-2d1f-44d4-a4dc6cfe9b88944b",
    created_at: "2026-06-09T00:00:00",
  },
  {
    id: "ev-jpeg-c",
    case_id: CASE_ID,
    filename: "17.jpg",
    original_filename: "17.jpg",
    file_size: 190000,
    file_type: "imagem",
    mime_type: "image/jpeg",
    sha256: "c".repeat(64),
    uploaded_by: "9a6920ec-2d1f-44d4-a4dc6cfe9b88944b",
    created_at: "2026-06-09T00:00:00",
  },
];

const ALL_PAIRS_MATRIX_RESULT = {
  success: true,
  mode: "all_pairs",
  reference_count: 0,
  questioned_count: 2,
  matrix: {
    row_labels: ["7.jpg", "27.jpg"],
    col_labels: ["7.jpg", "27.jpg"],
    rows: [
      {
        row_index: 0,
        evidence_id: "ev-jpeg-a",
        label: "7.jpg",
        cells: [
          { col_index: 0, matches: true },
          { col_index: 1, matches: false, reason: "matriz DQT diferente" },
        ],
      },
      {
        row_index: 1,
        evidence_id: "ev-jpeg-b",
        label: "27.jpg",
        cells: [
          { col_index: 0, matches: false, reason: "matriz DQT diferente" },
          { col_index: 1, matches: true },
        ],
      },
    ],
  },
  questioned_structures: [
    {
      available: true,
      evidence_id: "ev-jpeg-a",
      label: "7.jpg",
      comparison_markers: [
        { name: "SOI", display_name: "SOI" },
        { name: "DQT", display_name: "DQT", dqt_tables: [{ table_id: 0, precision: 0, matrix: Array(64).fill(8) }] },
        { name: "EOI", display_name: "EOI" },
      ],
    },
    {
      available: true,
      evidence_id: "ev-jpeg-b",
      label: "27.jpg",
      comparison_markers: [
        { name: "SOI", display_name: "SOI" },
        { name: "DQT", display_name: "DQT", dqt_tables: [{ table_id: 0, precision: 0, matrix: Array(64).fill(1) }] },
        { name: "EOI", display_name: "EOI" },
      ],
    },
  ],
  errors: [],
};

const WITH_REF_MATRIX_RESULT = {
  success: true,
  mode: "with_reference",
  reference_count: 2,
  questioned_count: 2,
  matrix: {
    row_labels: ["padrao_a.jpg", "padrao_b.jpg"],
    col_labels: ["7.jpg", "27.jpg"],
    rows: [
      {
        row_index: 0,
        evidence_id: "ref-a",
        label: "padrao_a.jpg",
        cells: [
          { col_index: 0, matches: true, questioned_evidence_id: "ev-jpeg-a" },
          { col_index: 1, matches: true, questioned_evidence_id: "ev-jpeg-b" },
        ],
      },
      {
        row_index: 1,
        evidence_id: "ref-b",
        label: "padrao_b.jpg",
        cells: [
          { col_index: 0, matches: false, questioned_evidence_id: "ev-jpeg-a" },
          { col_index: 1, matches: false, questioned_evidence_id: "ev-jpeg-b" },
        ],
      },
    ],
  },
  reference_structures: [
    {
      available: true,
      evidence_id: "ref-a",
      label: "padrao_a.jpg",
      comparison_markers: [
        { name: "SOI", display_name: "SOI" },
        { name: "EOI", display_name: "EOI" },
      ],
    },
    {
      available: true,
      evidence_id: "ref-b",
      label: "padrao_b.jpg",
      comparison_markers: [
        { name: "SOI", display_name: "SOI" },
        { name: "DQT", display_name: "DQT" },
        { name: "EOI", display_name: "EOI" },
      ],
    },
  ],
  questioned_structures: ALL_PAIRS_MATRIX_RESULT.questioned_structures,
  errors: [],
};

async function mockAuth(page: Page) {
  await page.route("**/api/v1/auth/login", async (route) => {
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
}

async function mockJpegStructureCaseApis(page: Page) {
  await page.route(`**/api/v1/cases/${CASE_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: CASE_ID,
        protocol_number: "2026/003",
        title: "Exemplo3",
        description: "Caso E2E JPEG estrutura",
        status: "aberto",
        created_by: "1",
        created_at: "2026-06-09T00:00:00",
        updated_at: "2026-06-09T00:00:00",
      }),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/evidences`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(JPEG_EVIDENCES),
    });
  });

  await page.route(`**/api/v1/cases/${CASE_ID}/references`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        groups: [
          {
            group_label: "Camera_X",
            technique: "jpeg_structure_compare",
            files: [
              {
                id: "ref-a",
                case_id: CASE_ID,
                filename: "padrao_a.jpg",
                original_filename: "padrao_a.jpg",
                file_size: 1000,
                file_type: "imagem",
                mime_type: "image/jpeg",
                sha256: "d".repeat(64),
                uploaded_by: "1",
                created_at: "2026-06-09T00:00:00",
              },
              {
                id: "ref-b",
                case_id: CASE_ID,
                filename: "padrao_b.jpg",
                original_filename: "padrao_b.jpg",
                file_size: 1000,
                file_type: "imagem",
                mime_type: "image/jpeg",
                sha256: "e".repeat(64),
                uploaded_by: "1",
                created_at: "2026-06-09T00:00:00",
              },
            ],
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/analysis/techniques", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { name: "jpeg_structure_compare", supported_types: ["imagem"], available: true },
        { name: "ela", supported_types: ["imagem"], available: true },
      ]),
    });
  });
}

async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[id="username"]', "e2euser");
  await page.fill('input[id="password"]', "E2ESenha123!");
  await page.click('button[type="submit"]');
  await page.waitForURL("/");
}

async function mockAnalysisJob(page: Page, result: Record<string, unknown>, jobId = "job-e2e-jpeg") {
  await page.route(/\/api\/v1\/analysis/, async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (method === "POST" && url.endsWith("/api/v1/analysis")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ job_id: jobId, progress: 5, progress_message: "Iniciando…" }),
      });
      return;
    }

    if (url.endsWith(`/analysis/${jobId}/result`)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(result),
      });
      return;
    }

    if (url.includes(`/analysis/${jobId}`) && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "completed",
          progress: 100,
          progress_message: "Concluido",
        }),
      });
      return;
    }

    await route.continue();
  });
}

test.describe("JPEG structure compare — fluxo E2E", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page);
    await mockJpegStructureCaseApis(page);
    await login(page);
  });

  test("carrega a pagina pelo card sem tela branca", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await page.goto(`/cases/${CASE_ID}/analysis/jpeg_structure_compare`);

    await expect(page.getByTestId("jpeg-structure-compare-page")).toBeVisible();
    await expect(page.locator("h1.analysis-page-shell__title")).toHaveText("Comparação de Estruturas JPEG");
    await expect(page.locator("text=Seleção de imagens JPEG")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Modo de comparação" })).toBeVisible();
    await expect(page.locator("text=Com referência (padrões)")).toBeVisible();
    await expect(page.locator("text=Sem referência (todas × todas)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Calcular" })).toBeVisible();
    await expect(page.locator("text=7.jpg").first()).toBeVisible();
    await expect(page.locator("text=Token de autenticacao invalido")).toHaveCount(0);

    expect(pageErrors).toEqual([]);
  });

  test("sem referencia: matriz com aliases e grade posicional", async ({ page }) => {
    await mockAnalysisJob(page, ALL_PAIRS_MATRIX_RESULT, "job-e2e-matrix");
    await page.goto(`/cases/${CASE_ID}/analysis/jpeg_structure_compare`);
    await page.click("text=Sem referência (todas × todas)");
    await page.getByRole("button", { name: "Calcular" }).click();

    await expect(page.locator('[data-testid="jpeg-matrix-cell"]').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("jpeg-matrix-legend")).toBeVisible();
    await expect(page.locator("text=Q1").first()).toBeVisible();
    const cells = page.locator('[data-testid="jpeg-matrix-cell"]');
    await expect(cells).toHaveCount(4);
    await expect(cells.nth(0)).toHaveText("✓");
    await expect(cells.nth(1)).toHaveText("✗");

    await expect(page.locator("text=Estruturas JPEG — grade posicional")).toBeVisible();
    await expect(page.locator('[data-testid="dqt-cell"]').first()).toBeVisible();
  });

  test("com referencia: padrões no topo e clique ativa comparação", async ({ page }) => {
    await mockAnalysisJob(page, WITH_REF_MATRIX_RESULT, "job-e2e-ref");
    await page.goto(`/cases/${CASE_ID}/analysis/jpeg_structure_compare`);

    await page.getByRole("button", { name: "Calcular" }).click();

    await expect(page.locator('[data-testid="jpeg-matrix-cell"]').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=R1").first()).toBeVisible();
    await expect(page.locator("text=Padrões de referência — clique para ativar")).toBeVisible();
    await expect(page.locator("text=padrao_a.jpg").first()).toBeVisible();

    await page.locator("text=padrao_b.jpg").first().click();
    await expect(page.locator(".jpeg-compare-grid__ref-badge").filter({ hasText: "REF" })).toBeVisible();
  });
});
