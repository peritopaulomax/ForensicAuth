import { test, expect } from "@playwright/test";

test("case detail with labeled evidences does not crash", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(String(err) + "\n" + (err.stack || "")));

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

  await page.route("**/api/v1/cases", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "case-1",
          protocol_number: "2024/001",
          title: "Caso Rotulo Crash",
          description: "",
          status: "aberto",
          created_by: "1",
          created_at: "2026-05-30T00:00:00",
          updated_at: "2026-05-30T00:00:00",
        },
      ]),
    });
  });

  await page.route("**/api/v1/cases/case-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "case-1",
        protocol_number: "2024/001",
        title: "Caso Rotulo Crash",
        description: "",
        status: "aberto",
        created_by: "1",
        created_at: "2026-05-30T00:00:00",
        updated_at: "2026-05-30T00:00:00",
      }),
    });
  });

  await page.route("**/api/v1/cases/case-1/closure-status", async (route) => {
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

  await page.route("**/api/v1/cases/case-1/derivatives", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.route("**/api/v1/cases/case-1/references**", async (route) => {
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

  await page.route("**/api/v1/cases/case-1/evidences", async (route) => {
    const items = Array.from({ length: 5 }, (_, i) => ({
      id: `ev-${i}`,
      case_id: "case-1",
      filename: `f${i}.jpg`,
      original_filename: `foto${i}.jpg`,
      file_size: 1000,
      file_type: "imagem",
      mime_type: "image/jpeg",
      sha256: "a".repeat(64),
      extra_metadata: { questioned_group_label: i < 3 ? "Camera A" : "Camera B" },
      uploaded_by: "1",
      created_at: "2026-01-01T00:00:00",
      group_label: i < 3 ? "Camera A" : "Camera B",
    }));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(items) });
  });

  await page.route("**/api/v1/evidences/*/thumbnail", async (route) => {
    await route.fulfill({ status: 404, body: "no" });
  });

  await page.goto("/login");
  await page.fill('input[id="username"]', "e2euser");
  await page.fill('input[id="password"]', "E2ESenha123!");
  await page.click('button[type="submit"]');
  await page.waitForURL("/");

  await page.click("text=Caso Rotulo Crash");
  await page.waitForURL("/cases/case-1");
  await expect(page.getByRole("heading", { name: "Camera A (3)" })).toBeVisible({ timeout: 10000 });
  await expect(page.getByRole("heading", { name: "Camera B (2)" })).toBeVisible();
  await expect(page.getByText("foto0.jpg").first()).toBeVisible();

  const fatal = errors.filter(
    (e) =>
      !e.includes("thumbnail") &&
      !e.includes("Failed to load") &&
      !e.includes("404") &&
      !e.includes("net::"),
  );
  expect(fatal).toEqual([]);
});
