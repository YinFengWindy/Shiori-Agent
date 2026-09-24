import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, type Locator, type Page } from "playwright";
import { configureSettingsConfigPath, loadSettingsData } from "../../src/settings";
import { fakeBridgeOfflineMessage, installOnboardingFakeBridge } from "./fakeBridge";

const url = process.env.SHIORI_QA_URL ?? "http://127.0.0.1:5187";
const output = resolve(".test-tmp-root/onboarding-qa");
await mkdir(output, { recursive: true });
configureSettingsConfigPath("qa.toml");
const initial = loadSettingsData("[llm]\n");
const browser = await chromium.launch({ executablePath: process.env.SHIORI_QA_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: true });
const errors: string[] = [];
/** Window sizes every step's primary action and 吟风's dialogue box must fit (the last is Electron's minimum). */
const layouts = [[1280, 800], [960, 640], [1920, 1080], [520, 680]] as const;

async function state(page: Page, patch: Record<string, unknown>) {
  await page.evaluate((patch) => {
    const value = JSON.parse(localStorage.getItem("qa.onboarding.bridge")!);
    localStorage.setItem("qa.onboarding.bridge", JSON.stringify({ ...value, ...patch }));
  }, patch);
  await page.reload();
}
function dialogue(page: Page) { return page.getByRole("region", { name: "吟风" }); }
/** Clicks through 吟风's lines (the scene, not the card) until a card heading appears. */
async function reveal(page: Page, name: string) {
  const target = page.getByRole("heading", { name, exact: true });
  for (let attempt = 0; attempt < 30 && !(await target.isVisible()); attempt += 1) {
    await page.getByRole("button", { name: "继续对话" }).dispatchEvent("click");
    await page.waitForTimeout(150);
  }
  await target.waitFor();
}
async function says(page: Page, text: string) { await dialogue(page).filter({ hasText: text }).waitFor(); }
async function assertInView(page: Page, locator: Locator, what: string) {
  const box = await locator.boundingBox();
  const viewport = page.viewportSize()!;
  assert.ok(box && box.y >= 0 && box.x >= 0 && box.y + box.height <= viewport.height && box.x + box.width <= viewport.width,
    `${what} must be fully visible at ${viewport.width}x${viewport.height}, got ${JSON.stringify(box)}`);
}
async function assertLayouts(page: Page, action: string, shot: string) {
  for (const [width, height] of layouts) {
    await page.setViewportSize({ width, height });
    await assertInView(page, page.getByRole("button", { name: action, exact: true }), `「${action}」`);
    await assertInView(page, dialogue(page), "dialogue box");
    await page.screenshot({ path: resolve(output, `${shot}-${width}x${height}.png`) });
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.addInitScript({ content: "globalThis.__name = (value) => value;" });
  await context.addInitScript(installOnboardingFakeBridge, initial);
  await context.route("**/qa-avatar.png", (route) => route.fulfill({ path: resolve("assets/shiori-app-icon.png"), contentType: "image/png" }));
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  page.on("pageerror", (error) => { errors.push(error.message); console.error(error.stack ?? error.message); });
  await page.goto(url);
  // First visit: 吟风 greets before the model card rises; every step stays listed.
  await says(page, "我是吟风");
  assert.equal(await page.getByRole("heading", { name: "注册模型" }).count(), 0);
  await reveal(page, "注册模型");
  assert.deepEqual(await page.getByRole("navigation", { name: "首次设置进度" }).getByRole("listitem").allInnerTexts().then((items) => items.filter(Boolean)), ["1\n模型", "2\n角色", "3\n开始"]);
  await assertLayouts(page, "保存并继续", "model");
  // 「跳过」: 吟风 answers, then the guide closes for this launch only.
  await page.getByRole("button", { name: "跳过" }).click();
  await says(page, "以后去设置里也能弄");
  await page.getByTestId("onboarding-page").waitFor({ state: "detached" });
  await page.reload();
  await page.locator(".app-frame").waitFor();
  await state(page, { sessionId: "launch-2" });
  await reveal(page, "注册模型");
  // An unreachable bridge shows the inline error area with its recovery actions.
  await state(page, { offline: true });
  await page.getByRole("alert").filter({ hasText: new RegExp(`^${fakeBridgeOfflineMessage}$`) }).waitFor();
  await says(page, "后台还没醒过来");
  assert.equal(await page.getByRole("button", { name: "保存并继续" }).count(), 0);
  await page.getByRole("button", { name: "模型注册设置" }).click();
  // The bridge recovers during the settings detour; coming back resumes at the
  // model step's own line instead of replaying the opening greeting.
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("qa:bridge", { detail: { offline: false } })));
  await page.getByRole("button", { name: "返回引导" }).click();
  await says(page, "首先给 Shiori 接上一个大模型");
  assert.equal(await dialogue(page).filter({ hasText: "我是吟风" }).count(), 0);
  await page.getByRole("heading", { name: "注册模型", exact: true }).waitFor();
  await state(page, { offline: false, failSave: true });
  await reveal(page, "注册模型");
  await page.getByRole("textbox", { name: "模型", exact: true }).fill("qa-model");
  await page.getByRole("button", { name: "测试连接" }).click();
  await page.getByRole("status").filter({ hasText: "连接成功" }).waitFor();
  await says(page, "通了通了");
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("qa:bridge", { detail: { connectionResult: { ok: false, message: "AuthenticationError: 401 Unauthorized" } } })));
  await page.getByRole("button", { name: "测试连接" }).click();
  await page.getByRole("status").filter({ hasText: "AuthenticationError: 401" }).waitFor();
  await says(page, "连不上");
  await page.getByRole("button", { name: "保存并继续" }).click();
  await page.getByRole("alert").filter({ hasText: "测试模型保存失败" }).waitFor();
  assert.equal(await page.getByRole("textbox", { name: "模型", exact: true }).inputValue(), "qa-model");
  await state(page, { failSave: false });
  await reveal(page, "注册模型");
  await page.getByRole("textbox", { name: "模型", exact: true }).fill("qa-model");
  await page.getByRole("button", { name: "保存并继续" }).click();
  await reveal(page, "创建角色");
  await state(page, { sessionId: "launch-3", failCreate: true });
  // A resumed guide skips the greeting and starts at its step.
  await says(page, "创建你的第一个角色");
  await reveal(page, "创建角色");
  await assertLayouts(page, "创建角色", "role");
  await page.getByRole("button", { name: "上传头像" }).click();
  await page.getByAltText("角色头像预览").waitFor();
  await says(page, "好可爱");
  assert.ok(await page.getByAltText("角色头像预览").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0));
  await page.getByRole("button", { name: "移除头像" }).click();
  await page.getByRole("button", { name: "上传头像" }).click();
  await page.getByTestId("new-role-name").fill("小诗");
  await page.getByRole("textbox", { name: "角色设定", exact: true }).fill("安静、细心");
  await page.getByRole("button", { name: "创建角色", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "测试头像保存失败" }).waitFor();
  await says(page, "没建成");
  assert.equal(await page.getByTestId("new-role-name").inputValue(), "小诗");
  assert.equal(await page.getByAltText("角色头像预览").count(), 1);
  await state(page, { failCreate: false, failReadsAfterCreate: true });
  await reveal(page, "创建角色");
  await page.getByTestId("new-role-name").fill("小诗");
  await page.getByRole("textbox", { name: "角色设定", exact: true }).fill("安静、细心");
  await page.getByRole("button", { name: "上传头像" }).click();
  await page.getByRole("button", { name: "创建角色", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: new RegExp(`^${fakeBridgeOfflineMessage}$`) }).waitFor();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("qa:bridge", { detail: { offline: false } })));
  await page.getByRole("button", { name: "重试连接" }).click();
  await says(page, "去和 小诗 打个招呼");
  await reveal(page, "小诗");
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("qa.onboarding.bridge")!).createCalls), 2);
  // The last step has nothing left to skip.
  assert.equal(await page.getByRole("button", { name: "跳过" }).count(), 0);
  await state(page, { sessionId: "launch-4" });
  await reveal(page, "小诗");
  await assertLayouts(page, "进入 Shiori", "workspace");
  await page.getByRole("button", { name: "进入 Shiori", exact: true }).click();
  await page.getByTestId("onboarding-page").waitFor({ state: "detached" });
  await state(page, { sessionId: "launch-5", roles: [] });
  await page.locator(".app-frame").waitFor();
  assert.equal(await page.getByTestId("onboarding-page").count(), 0);
  // A pre-existing registration exempts a user who has never enrolled in onboarding.
  await page.evaluate(() => { localStorage.removeItem("onboarding.v1"); sessionStorage.clear(); });
  await page.reload();
  await page.locator(".app-frame").waitFor();
  assert.equal(await page.getByTestId("onboarding-page").count(), 0);
  assert.deepEqual(errors, []);
  // Every bridge method the renderer called has a real-shaped fake payload.
  assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem("qa.onboarding.bridge")!).unknownMethods), []);
  console.log("PASS: greeting, step indicator, skip line, bridge/settings failure, connection test reactions, model save, role/avatar reactions and recovery, completion/relaunch, layouts 1280x800 / 960x640 / 1920x1080 / 520x680");
} finally { await browser.close(); }
