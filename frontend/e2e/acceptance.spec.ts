import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const SHOTS = process.env.E2E_SCREENSHOTS;
let fixtures: string;

test.beforeAll(() => {
  fixtures = fs.mkdtempSync(path.join(os.tmpdir(), "mg-e2e-"));
  const backend = path.resolve(__dirname, "../../backend");
  const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
  execFileSync(python, ["-c", `
import sys; sys.path.insert(0, ${JSON.stringify(backend)})
from pathlib import Path
from tests.fixtures_gen import make_pdf, make_pptx
d = Path(${JSON.stringify(fixtures)})
make_pdf(d / "Cardiac Anatomy.pdf"); make_pptx(d / "Brachial Plexus.pptx")`]);
});

async function shot(page: import("@playwright/test").Page, name: string) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

test("MVP acceptance: upload, view, tutor with citations, quiz, progress", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByText("Start by uploading a medical document").or(page.getByText("Recently uploaded"))).toBeVisible();
  await shot(page, "01-dashboard-empty");

  // 2-3. upload a real PDF and PowerPoint
  await page.goto("/library");
  await page.getByTestId("file-input").setInputFiles([path.join(fixtures, "Cardiac Anatomy.pdf"), path.join(fixtures, "Brachial Plexus.pptx")]);
  await page.getByRole("button", { name: /Upload 2 files/ }).click();
  await expect(page.getByText(/document\(s\) uploaded/)).toBeVisible();
  const cards = page.getByTestId("document-card");
  await expect(cards.filter({ hasText: "Cardiac Anatomy" }).getByText(/3 pages/)).toBeVisible({ timeout: 90_000 });
  await expect(cards.filter({ hasText: "Brachial Plexus" }).getByText(/3 slides/)).toBeVisible({ timeout: 90_000 });
  await shot(page, "02-library");

  // 4-5. open workspace, see extracted pages and original rendering
  await page.getByRole("link", { name: "Cardiac Anatomy" }).first().click();
  await expect(page.getByRole("button", { name: /Anatomy of the Heart/ }).first()).toBeVisible();
  await expect(page.getByAltText(/Page 1 of Cardiac Anatomy/)).toBeVisible();
  await page.getByRole("button", { name: /Cardiac Conduction System/ }).first().click();
  await page.getByRole("radio", { name: "Extracted" }).click();
  await expect(page.getByText("Purkinje fibres", { exact: false })).toBeVisible();
  await shot(page, "03-workspace-extracted");

  // 6-10. ask a question at beginner level, get explanation with citations, follow up
  await page.getByRole("radio", { name: /^1/ }).first().click();
  await page.getByLabel("Message").fill("Which valve is between the left atrium and the left ventricle?");
  await page.getByTitle("Send").click();
  await expect(page.getByText("From your documents").first()).toBeVisible();
  await expect(page.getByText(/Local · llama3.1:8b/)).toBeVisible();
  await expect(page.getByText(/Sources cited/)).toBeVisible();
  await shot(page, "04-tutor-answer");
  const chip = page.locator("button[title*='Cardiac Anatomy — page']").first();
  const title = (await chip.getAttribute("title")) ?? "";
  const cited = Number(title.match(/page (\d+)/)?.[1]);
  await chip.click();
  await expect(page.getByLabel("Page number")).toHaveValue(String(cited));
  await page.getByRole("button", { name: "Clinical correlation" }).click();
  await expect(page.locator("div.prose-med").nth(1)).toBeVisible();
  // advanced level follow-up
  await page.getByRole("radio", { name: /^3/ }).first().click();
  await page.getByLabel("Message").fill("Explain more about the left ventricle");
  await page.getByTitle("Send").click();
  await expect(page.getByText("L3 · Advanced")).toBeVisible();

  // PPTX slide view
  await page.goto("/library");
  await page.getByRole("link", { name: "Brachial Plexus" }).first().click();
  await expect(page.getByLabel("Slide number")).toBeVisible();
  await page.getByRole("radio", { name: "Extracted" }).click();
  await expect(page.getByText("Real Texans Drink Cold Beer")).toBeVisible();
  await shot(page, "05-pptx-notes");

  // 11-12. generate MCQs, answer, submit, see explanations
  await page.goto("/practice");
  await page.getByRole("button", { name: "Cardiac Anatomy" }).first().click();
  await page.getByRole("button", { name: "Short answer" }).click();
  await page.getByRole("button", { name: "Start examination" }).click();
  await expect(page.getByText("Which valve separates the left atrium")).toBeVisible();
  await page.getByText("Tricuspid valve").click(); // deliberately wrong
  await page.getByRole("button", { name: "True" }).click();
  await page.getByLabel("Answer").fill("Because it pumps at high pressure into the systemic circulation.");
  await shot(page, "06-quiz");
  await page.getByRole("button", { name: "Submit answers" }).click();
  await expect(page.getByText("Results")).toBeVisible();
  await expect(page.getByText("Weak areas")).toBeVisible();
  await expect(page.getByText("Supported by:").first()).toBeVisible();
  await shot(page, "07-results");

  // 13. progress saved
  await page.goto("/progress");
  await expect(page.getByText("Heart valves")).toBeVisible();
  await page.goto("/revision");
  await expect(page.getByText("From mistake").first()).toBeVisible();
  await shot(page, "08-revision");

  // 14. data persisted server-side (restart is covered by scripts/run-e2e: re-run with same data dir)
  const docs = await (await request.get(`${API}/api/documents`)).json();
  expect(docs.length).toBeGreaterThanOrEqual(2);
});

test("mobile layout uses tabs instead of three columns", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
  const page = await ctx.newPage();
  await page.goto("/library");
  await page.getByRole("link", { name: "Cardiac Anatomy" }).first().click();
  await expect(page.getByRole("radio", { name: "AI Tutor" })).toBeVisible();
  await page.getByRole("radio", { name: "AI Tutor" }).click();
  await expect(page.getByLabel("Message")).toBeVisible();
  await shot(page, "09-mobile-tutor");
  await ctx.close();
});
