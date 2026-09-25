import assert from "node:assert/strict";
import { mkdir, mkdtemp } from "node:fs/promises";
import { resolve } from "node:path";
import { _electron, type Page } from "playwright";

const output = resolve(".test-tmp-root/onboarding-qa");
await mkdir(output, { recursive: true });
const isolated = await mkdtemp(resolve(output, "electron-run-"));
const home = resolve(isolated, "home");
await mkdir(home);
async function launch() {
  const app = await _electron.launch({
    executablePath: resolve("apps/desktop/node_modules/electron/dist/electron.exe"),
    args: [resolve("apps/desktop/tests/onboarding/electronBootstrap.cjs")],
    env: { ...process.env, SHIORI_QA_HOME: home, SHIORI_DESKTOP_USER_DATA_DIR: resolve(isolated, "user-data"),
      SHIORI_RENDERER_DEV_SERVER_URL: process.env.SHIORI_QA_URL ?? "http://127.0.0.1:5187" },
  });
  // The hidden plugin-host background window may open before the main window.
  const isMainWindow = (window: Page) => new URL(window.url()).pathname.replace(/\/index\.html$/, "/") === "/";
  const page = app.windows().find(isMainWindow) ?? await app.waitForEvent("window", { predicate: isMainWindow });
  page.setDefaultTimeout(20_000);
  return { app, page };
}
/** Clicks through 吟风's lines until the step's card heading appears. */
async function reveal(page: Page, name: string) {
  const target = page.getByRole("heading", { name, exact: true });
  for (let attempt = 0; attempt < 40 && !(await target.isVisible()); attempt += 1) {
    await page.getByRole("button", { name: "继续对话" }).dispatchEvent("click").catch(() => undefined);
    await page.waitForTimeout(200);
  }
  await target.waitFor();
}
let current = await launch();
try {
  await reveal(current.page, "注册模型");
  await current.page.getByRole("button", { name: "跳过" }).click();
  await current.page.locator(".app-frame").waitFor();
  await current.page.reload();
  await current.page.locator(".app-frame").waitFor();
  await current.app.close();
  current = await launch();
  await reveal(current.page, "注册模型");
  await current.page.getByRole("textbox", { name: "模型", exact: true }).fill("onboarding-qa");
  await current.page.getByRole("textbox", { name: "服务地址", exact: true }).fill("http://127.0.0.1:9/v1");
  await current.page.getByLabel("API Key", { exact: true }).fill("local-test-only");
  await current.page.getByRole("button", { name: "保存并继续" }).click();
  await reveal(current.page, "创建角色");
  await current.app.close();
  current = await launch();
  await reveal(current.page, "创建角色");
  // Stub only the OS dialog selection; image import, capabilities, and backend persistence are real.
  await current.app.evaluate(({ dialog }, path) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] });
  }, resolve("assets/shiori-app-icon.png"));
  await current.page.getByRole("button", { name: "上传头像" }).click();
  await current.page.getByAltText("角色头像预览").waitFor();
  await current.page.getByTestId("new-role-name").fill("新手引导验证");
  await current.page.getByRole("textbox", { name: "角色设定", exact: true }).fill("安静、细心，回答简洁。");
  await current.page.getByRole("button", { name: "创建角色", exact: true }).click();
  await reveal(current.page, "新手引导验证");
  await current.app.close();
  current = await launch();
  await reveal(current.page, "新手引导验证");
  const avatar = current.page.getByAltText("新手引导验证");
  await avatar.waitFor();
  assert.ok(await avatar.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0));
  await current.page.screenshot({ path: resolve(output, "electron-workspace.png") });
  await current.page.getByRole("button", { name: "进入 Shiori", exact: true }).click();
  await current.page.locator(".app-frame").waitFor();
  await current.app.close();
  current = await launch();
  await current.page.locator(".app-frame").waitFor();
  assert.equal(await current.page.getByTestId("onboarding-page").count(), 0);
  console.log("PASS: real Electron and Python bridge, skip/reload, four relaunches, model registration, avatar import, role creation, workspace entry, completed restart");
} finally { await current.app.close(); }
