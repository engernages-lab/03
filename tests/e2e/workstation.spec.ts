import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import path from "node:path";

// The spec is compiled as CommonJS, so __dirname is tests/e2e.
const FIXTURES = path.resolve(__dirname, "..", "fixtures");
const WAV = path.join(FIXTURES, "tone.wav");
const MIDI = path.join(FIXTURES, "sample.mid");

/** Note count from the compiled score stats ("音符 12"), or -1 when absent. */
async function noteCount(page: Page): Promise<number> {
  const text = await page.getByText(/音符 \d+/).first().textContent();
  const match = text?.match(/音符\s*(\d+)/);
  return match ? Number(match[1]) : -1;
}

test.describe.configure({ mode: "serial" });

test("工作台展示真实系统状态与能力探测", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("工作台");
  await expect(page.getByText("运行时能力探测")).toBeVisible();
  // capability rows come from the live /health probe
  await expect(page.getByText("FFmpeg", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("librosa", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/可用/).first()).toBeVisible();
});

test("导入本地音乐 → 播放 → 检查扒谱资格 → 进入分析输入", async ({ page }) => {
  // Deterministic starting state: the local source must not have AI consent yet.
  await page.request.put("/api/v1/sources/local/permissions", {
    data: { ai_processing_permission: false, model_training_permission: false },
  });

  await page.goto("/music-library");
  await expect(page.getByRole("button", { name: /导入本地音乐/ })).toBeVisible();

  // folder authorisation: the picker must expose webkitdirectory-style access
  await expect(page.getByRole("button", { name: /导入文件夹/ })).toBeVisible();
  const folderInputCount = await page
    .locator('input[type="file"][webkitdirectory]')
    .count();
  expect(folderInputCount).toBeGreaterThan(0);

  // 1. import a local audio file through the hidden file input
  const fileInput = page.locator('input[type="file"][accept*=".wav"]').first();
  await fileInput.setInputFiles(WAV);
  await expect(page.getByText(/成功导入 1 个音频文件/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("tone")).toBeVisible();

  // 2. play it and verify the audio element receives a real stream URL
  await page.getByRole("button", { name: /播放 tone/ }).first().click();
  const player = page.locator("audio");
  await expect(player).toHaveAttribute("src", /\/api\/v1\/audio\/assets\/.*\/stream/, { timeout: 15_000 });

  // 3. eligibility check on the transcription page
  await page.goto("/transcription");
  await expect(page.getByText("扒谱能力的真实状态")).toBeVisible();
  await expect(page.getByText(/REQUIRES_MODEL|不可用/)).toBeVisible();

  const select = page.locator("select").first();
  const options = await select.locator("option").allTextContents();
  const localOption = options.find((option) => option.includes("(local)"));
  expect(localOption, "local track should be selectable for eligibility").toBeTruthy();
  await select.selectOption({ label: localOption! });

  // 4. the verdict is shown with per-permission breakdown
  await expect(page.getByText("REQUIRES_PERMISSION")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("ai processing permission")).toBeVisible();
  await expect(page.getByText(/尚未获得用于 AI 扒谱的授权/)).toBeVisible();

  // 5. grant the AI-processing permission in the sources UI (explicit user consent)
  await page.goto("/music-sources");
  const consent = page.getByLabel(/AI 处理授权/);
  await expect(consent).toBeVisible();
  await consent.check();
  await expect(consent).toBeChecked();

  // 6. back on the transcription page the verdict flips to ELIGIBLE and a job can be created
  await page.goto("/transcription");
  await page.locator("select").first().selectOption({ label: localOption! });
  await expect(page.getByText("ELIGIBLE")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "创建分析作业", exact: true }).click();
  await expect(page.getByText(/已创建分析作业/)).toBeVisible({ timeout: 15_000 });

  // 7. the job runs the real signal analysis and refuses to invent notes.
  //    Scope assertions to the job card: the page also contains explanatory
  //    prose mentioning "analysis_only", which must not satisfy the check.
  const jobCard = page.getByTestId("job-card").first();
  await expect(jobCard).toBeVisible({ timeout: 15_000 });
  await expect(jobCard.getByText("analysis_only", { exact: true })).toBeVisible({ timeout: 120_000 });
  await expect(jobCard.getByText(/生成音符 0 个/)).toBeVisible();
  await expect(jobCard.getByText(/未内置扒谱模型/)).toBeVisible({ timeout: 15_000 });
});

test("导入 MIDI → 生成格子谱 → 切换数字谱 → 编辑音符并保持同步", async ({ page }) => {
  await page.goto("/scores");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("我的谱面");

  // import the MIDI fixture
  const midiInput = page.locator('input[type="file"][accept*=".mid"]').first();
  await midiInput.setInputFiles(MIDI);

  // editor loads with both notations
  await page.waitForURL(/\/scores\/[0-9a-zA-Z]+$/, { timeout: 30_000 });
  await expect(page.getByText("双谱对照")).toBeVisible();
  await expect(page.getByText("键位")).toBeVisible();
  await expect(page.getByText(/1 = C/)).toBeVisible();

  // stats come from the compiled view model
  await expect(page.getByText(/音符 \d+/).first()).toBeVisible();

  // add a note by clicking an empty grid cell in the first key row
  const countBefore = await noteCount(page);
  const emptyCell = page.locator('button[title^="点击在第 1 小节写入 C4"]').first();
  await emptyCell.click();
  // The save is asynchronous, so wait for the observable outcome (compiled
  // stats) instead of a transient "saving" label.
  await expect.poll(() => noteCount(page), { timeout: 20_000 }).toBeGreaterThan(countBefore);

  // select the newly created note and delete it via toolbar
  const noteCells = page.locator('button[title*="C4 · 第 1 小节"]');
  await noteCells.first().click();
  await expect(page.getByText("已选音符")).toBeVisible();
  await page.getByRole("button", { name: /删除音符/ }).click();
  await expect(page.getByText("已选音符")).toHaveCount(0, { timeout: 15_000 });
  await expect.poll(() => noteCount(page), { timeout: 20_000 }).toBe(countBefore);

  // switch to jianpu-only view and back
  await page.getByRole("button", { name: "数字谱", exact: true }).click();
  await expect(page.getByText("1 = C")).toBeVisible();
  await page.getByRole("button", { name: "双谱对照" }).click();

  // undo restores the previous document snapshot
  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.getByText(/音符 \d+/).first()).toBeVisible();

  // export endpoints respond with real files
  const exportResponse = await page.request.get(
    `${await page.evaluate(() => window.location.origin)}/api/v1/notation/${page.url().split("/").pop()}/grid.svg`,
  );
  expect(exportResponse.status()).toBe(200);
  expect(await exportResponse.text()).toContain("<svg");
});

test("保存的谱面可以重新打开并保留数据", async ({ page }) => {
  await page.goto("/scores");
  const firstScore = page.locator('a[href^="/scores/"]').first();
  const href = await firstScore.getAttribute("href");
  expect(href).toBeTruthy();

  await firstScore.click();
  await page.waitForURL(/\/scores\/[0-9a-zA-Z]+$/);
  await expect(page.getByText("双谱对照")).toBeVisible();
  await expect(page.getByText(/音符 \d+/).first()).toBeVisible();

  // reload to prove the document is persisted server-side
  await page.reload();
  await expect(page.getByText("双谱对照")).toBeVisible();
  await expect(page.getByText(/音符 \d+/).first()).toBeVisible();
});

test("键盘布局编辑器可以修改键位并影响谱面", async ({ page }) => {
  await page.goto("/keyboard");
  await expect(page.getByText("键盘预览")).toBeVisible();
  await expect(page.getByText("键位定义")).toBeVisible();

  // builtin layouts are read-only; the editor offers a copy
  await expect(page.getByText("内置布局（只读）")).toBeVisible();
  await page.getByRole("button", { name: /复制为可编辑/ }).click();
  await expect(page.getByText(/已基于内置布局创建可编辑副本/)).toBeVisible({ timeout: 20_000 });

  // edit the first key label
  const labelInput = page.locator("tbody input[type=text]").first();
  await labelInput.fill("低音Do");
  await page.getByRole("button", { name: /^保存$/ }).click();
  await expect(page.getByText("布局已保存")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("低音Do")).toBeVisible();
});

test("音乐来源页如实标注各平台可用性", async ({ page }) => {
  await page.goto("/music-sources");
  await expect(page.getByText("已连接的音乐来源")).toBeVisible();
  await expect(page.getByText("Navidrome / OpenSubsonic")).toBeVisible();
  await expect(page.getByText("Spotify", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "网易云音乐" })).toBeVisible();
  await expect(page.getByText(/政策禁止|无法获取内容/).first()).toBeVisible();
});
