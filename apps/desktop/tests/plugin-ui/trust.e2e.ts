import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { _electron, type ElectronApplication, type Page } from "playwright";

await mkdir(".test-tmp-root", { recursive: true });
const output = await mkdtemp(resolve(".test-tmp-root", "plugin-trust-real-"));
const home = resolve(output, "home");
const workspace = resolve(home, ".shiori", "workspace");
const packageRoot = resolve(workspace, "plugins", "manual_trust_qa");
const trustFile = resolve(workspace, "private_runtime", "plugin-trust.json");
const executionFile = resolve(workspace, "backend-executions.txt");
await mkdir(resolve(packageRoot, "backend"), { recursive: true });
await mkdir(resolve(packageRoot, "ui", "dist"), { recursive: true });
await writeFile(resolve(workspace, "config.toml"), "[llm]\nregistrations = []\n[agent.maintenance]\nmemory_optimizer_enabled = false\n[plugins.desktop_pet]\nenabled = false\n", "utf8");
await writeFile(resolve(packageRoot, "manifest.yaml"), `api: 4
sdk: ">=4.0.0"
id: manual_trust_qa
version: 1.0.0
entry: backend/plugin.py
inject: [rpc]
peer_dependencies: {react: '>=19.2.0 <20.0.0', react-dom: '>=19.2.0 <20.0.0'}
renderer:
  ui: {entry: ui/dist/index.mjs, css: [ui/dist/style.css]}
`, "utf8");
await writeFile(resolve(packageRoot, "backend", "plugin.py"), "from pathlib import Path\nwith (Path(__file__).parents[3] / 'backend-executions.txt').open('a', encoding='utf-8') as marker: marker.write('executed\\n')\nasync def ping(payload): return {'pong': payload.get('value')}\nfrom shiori_sdk.core.services import RPC\nasync def setup(ctx): ctx.require(RPC).register('ping', ping)\n", "utf8");
const entryPath = resolve(packageRoot, "ui", "dist", "index.mjs");
await writeFile(entryPath, `import React, {useState} from 'react';
document.documentElement.dataset.manualTrustExecuted = 'true';
function View({client}) {
  const [count, setCount] = useState(0);
  const [reply, setReply] = useState('');
  return React.createElement('section', {className:'manual-trust-qa'},
    React.createElement('h1', null, '已信任插件 · 版本 1'),
    React.createElement('button', {onClick:()=>setCount(count+1)}, '点击计数 '+count),
    React.createElement('button', {onClick:async()=>setReply('RPC '+(await client.call('ping',{value:42})).pong)}, '调用后端'),
    React.createElement('p', {role:'status'}, reply));
}
export default {pluginId:'manual_trust_qa',navPage:{label:'手动信任验证',component:View}};
`, "utf8");
await writeFile(resolve(packageRoot, "ui", "dist", "style.css"), ".manual-trust-qa { padding: 2rem; } .manual-trust-qa button { margin: 1rem; padding: 1rem; }", "utf8");

let app: ElectronApplication | undefined;
let page: Page | undefined;
const rendererErrors: string[] = [];
const screenshot = async (name: string) => page!.screenshot({ path: resolve(output, `${name}.png`) });
async function launch() {
  const env = { ...process.env, SHIORI_QA_HOME: home, SHIORI_DESKTOP_USER_DATA_DIR: resolve(output, "user-data") };
  delete env.SHIORI_RENDERER_DEV_SERVER_URL;
  delete env.ELECTRON_RUN_AS_NODE;
  app = await _electron.launch({ executablePath: resolve("apps/desktop/node_modules/electron/dist/electron.exe"), args: [resolve("apps/desktop/tests/plugin-ui/trustBootstrap.cjs")], env, timeout: 45_000 });
  for (let attempt = 0; attempt < 300; attempt += 1) {
    page = app.windows().find((candidate) => candidate.url().endsWith("/index.html"));
    if (page) break;
    await new Promise((done) => setTimeout(done, 100));
  }
  assert.ok(page, "main renderer did not open");
  page.setDefaultTimeout(30_000);
  page.on("pageerror", (error) => rendererErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") rendererErrors.push(message.text()); });
  await page.getByRole("button", { name: "跳过", exact: true }).click();
  await page.locator(".app-frame").waitFor();
}
async function openPluginSettings() {
  assert.ok(page);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "插件", exact: true }).click();
}
async function close() { await app?.close(); app = undefined; page = undefined; }
function row() { return page!.locator('[data-plugin-row="manual_trust_qa"]'); }
async function trust() {
  await page!.getByRole("dialog", { name: "信任插件" }).getByRole("button", { name: "确认信任", exact: true }).click();
  await page!.getByRole("button", { name: "手动信任验证", exact: true }).waitFor();
}
try {
  await launch();
  const dialog = page!.getByRole("dialog", { name: "信任插件" });
  await dialog.waitFor();
  assert.ok((await dialog.innerText()).includes(packageRoot));
  await dialog.locator('[data-testid="confirm-persona"]').waitFor();
  assert.equal(await access(executionFile).then(() => true, () => false), false);
  assert.equal(await page!.locator('html[data-manual-trust-executed]').count(), 0);
  await screenshot("01-startup-confirmation");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  assert.equal(await access(trustFile).then(() => true, () => false), false);
  const reconnected = await page!.evaluate(() => window.miraDesktop.restartBridge());
  assert.equal(reconnected.ok, true);
  const sameSession = await page!.evaluate(async () => window.miraDesktop.invoke({ method: "plugins.list", payload: {} }));
  const pendingAfterReconnect = sameSession.payload.plugins.find((plugin: { id: string }) => plugin.id === "manual_trust_qa");
  assert.equal(pendingAfterReconnect.state, "UNTRUSTED");
  await openPluginSettings();
  await row().getByText("未信任", { exact: true }).waitFor();
  assert.equal(await dialog.count(), 0, "cancelled content must not prompt after bridge reconnect");
  assert.equal(await access(executionFile).then(() => true, () => false), false);
  await screenshot("02-cancelled-after-reconnect");
  await row().getByRole("button", { name: "信任…", exact: true }).click();
  await screenshot("03-manual-retry");
  await trust();
  assert.deepEqual((await readFile(executionFile, "utf8")).trim().split(/\r?\n/), ["executed"]);
  assert.equal(await page!.locator('html[data-manual-trust-executed="true"]').count(), 1);
  const firstApproval = await readFile(trustFile, "utf8");
  await page!.getByRole("button", { name: "手动信任验证", exact: true }).click();
  await page!.getByRole("button", { name: "点击计数 0", exact: true }).click();
  await page!.getByRole("button", { name: "点击计数 1", exact: true }).waitFor();
  await page!.getByRole("button", { name: "调用后端", exact: true }).click();
  await page!.getByText("RPC 42", { exact: true }).waitFor();
  await screenshot("04-active-hooks-rpc");
  await close();

  await launch();
  await page!.getByRole("button", { name: "手动信任验证", exact: true }).waitFor();
  assert.equal(await page!.getByRole("dialog", { name: "信任插件" }).count(), 0);
  await close();
  const beforeChangedStartup = await readFile(executionFile, "utf8");
  await writeFile(entryPath, (await readFile(entryPath, "utf8")).replace("版本 1", "版本 2"), "utf8");
  await launch();
  await page!.getByRole("dialog", { name: "信任插件" }).waitFor();
  assert.equal(await readFile(executionFile, "utf8"), beforeChangedStartup);
  assert.equal(await page!.getByRole("button", { name: "手动信任验证", exact: true }).count(), 0);
  assert.equal(await page!.locator('link[rel="stylesheet"][href^="shiori-plugin:"]').count(), 0);
  assert.deepEqual(rendererErrors.filter((message) => /manual_trust_qa|shiori-plugin|plugin-ui/i.test(message)), []);
  await screenshot("05-update-untrusted");
  await trust();
  assert.notEqual(await readFile(trustFile, "utf8"), firstApproval);
  await page!.getByRole("button", { name: "手动信任验证", exact: true }).click();
  await page!.getByRole("heading", { name: "已信任插件 · 版本 2", exact: true }).waitFor();
  await screenshot("06-new-content-active");
  await close();
  assert.ok(packageRoot.startsWith(workspace + sep));
  await rm(packageRoot, { recursive: true });
  await launch();
  assert.equal(await page!.getByText("manual_trust_qa", { exact: true }).count(), 0);
  assert.equal(await page!.getByRole("button", { name: "手动信任验证", exact: true }).count(), 0);
  assert.equal(await page!.locator('link[rel="stylesheet"][href^="shiori-plugin:"]').count(), 0);
  assert.deepEqual(rendererErrors.filter((message) => /manual_trust_qa|shiori-plugin|plugin-ui/i.test(message)), []);
  await screenshot("07-removed");
  await writeFile(resolve(output, "evidence.json"), JSON.stringify({ passed: true, startupPrompt: true, personaDialog: true, noExecutionBeforeApproval: true, cancelSurvivesBridgeReconnect: true, immediateBackendAndUi: true, realRpc: true, unchangedRestartSkipsPrompt: true, changedContentRequiresApproval: true, removedWithoutResidualUi: true, output }, null, 2), "utf8");
  console.log(`PASS real workspace trust: startup persona dialog, no execution before approval, cancel across bridge reconnect, immediate hooks + RPC, remembered unchanged content, changed content requires new approval, removal without residual UI/CSS. Screenshots and evidence: ${output}`);
} catch (error) {
  if (page) { await screenshot("failure"); console.error((await page.locator("body").innerText()).slice(0, 2500)); }
  throw error;
} finally { await close(); }
