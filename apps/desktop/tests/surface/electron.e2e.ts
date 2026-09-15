import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { _electron } from "playwright";

// Run from the repository root after pnpm build. Vite only supplies renderer
// modules; all window creation, paint events, focus and ready IPC are Electron.
const builtRenderer = process.env.SHIORI_QA_BUILT === "1";
const fullscreenWitness = process.env.SHIORI_QA_FULLSCREEN === "1";
const output = resolve(".test-tmp-root/surface-qa", builtRenderer ? "built-renderer" : ".", fullscreenWitness ? "fullscreen" : ".");
await mkdir(output, { recursive: true });
const isolated = await mkdtemp(resolve(output, "run-"));
const desktopRequire = createRequire(resolve("apps/desktop/package.json"));
const { createServer } = await import(pathToFileURL(desktopRequire.resolve("vite")).href);
const server = await createServer({
  configFile: resolve("apps/desktop/renderer/vite.config.ts"),
  server: { host: "127.0.0.1", port: 5194, strictPort: true },
});
await server.listen();
const launch = () => _electron.launch({
  executablePath: desktopRequire("electron"),
  args: [resolve("apps/desktop/tests/surface/electronBootstrap.mjs")],
  env: { ...process.env, SHIORI_QA_USER_DATA: isolated, SHIORI_RENDERER_DEV_SERVER_URL: builtRenderer ? "" : "http://127.0.0.1:5194" },
});
let app = await launch();
const log: string[] = [];
const results: Record<string, unknown> = {};
const topmostFailures: string[] = [];
let scenario = "";
let releaseEntry = () => {};
let entryBlocked = Promise.resolve();
async function installRoutes() {
app.process().stderr?.on("data", (chunk) => log.push(String(chunk)));
await app.context().route("**/src/surface/main.tsx", async (route) => { await entryBlocked; await route.continue(); });
await app.context().route("**/assets/surface-*.js", async (route) => { await entryBlocked; await route.continue(); });
await app.context().route("**/src/surface/pluginSurfaceModules.ts", async (route) => {
  if (scenario === "module") {
    await route.fulfill({ contentType: "text/javascript", body: 'throw new Error("QA module import exploded");' });
  } else if (scenario === "mount") {
    await route.fulfill({ contentType: "text/javascript", body: `
      import { pluginSurfaceRegistry } from "/src/surface/pluginSurfaceRegistry.ts";
      pluginSurfaceRegistry.register({slot:"desktop.surface",pluginId:"qa_mount",Component:function Broken(){throw new Error("QA component mount exploded");}});
    ` });
  } else await route.continue();
});
}
await installRoutes();

async function restart() {
  await app.close();
  app = await launch();
  await installRoutes();
  const witness = await app.firstWindow();
  await witness.waitForLoadState();
}

// Bootstrap globals are deliberately test-only and never exported by app code.
const qa = async (method: string, ...args: unknown[]) => app.evaluate(async (_electron, { method, args }) => {
  await (globalThis as any).surfaceQaReady;
  return (globalThis as any).surfaceQa[method](...args);
}, { method, args });

try {
  await app.firstWindow();
  results.environment = await app.evaluate(() => ({ platform: process.platform, electron: process.versions.electron, fullscreenWitness: process.env.SHIORI_QA_FULLSCREEN === "1" }));
  await app.evaluate(async () => {
    await (globalThis as any).surfaceQaReady;
    if (!(globalThis as any).surfaceQa) throw new Error("surface harness did not start");
  });
  results.paintGate = await qa("nativePaintGate", false);
  assert.deepEqual(results.paintGate, { beforePaint: false, afterPaint: true });
  results.cancelBeforePaint = await qa("nativePaintGate", true);
  assert.deepEqual(results.cancelBeforePaint, { beforePaint: false, afterPaint: false });
  // Isolate native helper HWND lifetimes from the production-window scenarios.
  await restart();

  const icon = `data:image/png;base64,${(await readFile(resolve("assets/shiori-app-icon.png"))).toString("base64")}`;
  // A complete fixture atlas keeps every real pet animation cell drawable.
  const atlas = `<svg xmlns="http://www.w3.org/2000/svg" width="1536" height="2288"><defs><pattern id="cell" width="192" height="208" patternUnits="userSpaceOnUse"><image href="${icon}" x="24" y="32" width="144" height="144"/></pattern></defs><rect width="100%" height="100%" fill="url(#cell)"/></svg>`;
  const sprite = `data:image/svg+xml;base64,${Buffer.from(atlas).toString("base64")}`;
  for (const [name, pluginId, detail] of [
    ["pet", "desktop_pet", ""],
    ["not-topmost", "not_topmost", "未提供桌面窗口"],
    ["missing", "", "窗口参数缺失"],
    ["unregistered", "not_registered", "未提供桌面窗口"],
    ["module", "qa_module", "插件模块加载失败"],
    ["mount", "qa_mount", "插件组件挂载失败"],
  ]) {
    if (builtRenderer && (name === "module" || name === "mount")) continue;
    scenario = name;
    entryBlocked = new Promise<void>((done) => { releaseEntry = done; });
    const pageReady = app.waitForEvent("window");
    const alwaysOnTop = name !== "not-topmost";
    const id = await qa("create", pluginId, name === "pet" ? sprite : undefined, alwaysOnTop);
    const page = await pageReady;
    const before = await qa("snapshot", id);
    assert.equal(before.initiallyVisible, false, `${name}: construction hidden`);
    assert.equal(before.visible, false, `${name}: early show hidden`);
    assert.equal(before.readyCount, 0);
    assert.equal(before.witnessFullScreen, fullscreenWitness);
    if (before.alwaysOnTop !== alwaysOnTop) topmostFailures.push(`${name}: construction`);
    releaseEntry();
    if (detail) await page.getByRole("alert").filter({ hasText: detail }).waitFor();
    else await page.locator(".pet-surface").waitFor();
    await page.waitForFunction(() => document.readyState === "complete");
    let after = await qa("snapshot", id);
    for (let attempt = 0; !after.visible && attempt < 100; attempt++) {
      await new Promise((done) => setTimeout(done, 50));
      after = await qa("snapshot", id);
    }
    results[name] = { before, after };
    assert.equal(after.visible, true, `${name}: ready content visible`);
    assert.equal(after.focused, false, `${name}: no focus stealing`);
    // The user may switch apps during QA; a surface must never receive focus,
    // regardless of which external window is currently in the foreground.
    assert.equal(after.events.includes("focus"), false, `${name}: no transient focus stealing`);
    if (after.alwaysOnTop !== alwaysOnTop) topmostFailures.push(name);
    assert.ok(after.events.indexOf("ready") < after.events.indexOf("show"));
    // The adapter's ready-to-show listener runs before the diagnostic listener,
    // so show can be recorded immediately before paint when ready arrived first.
    assert.ok(after.events.includes("paint"));
    const backgrounds = await page.evaluate(() => [document.documentElement, document.body, document.getElementById("root")!].map((node) => {
      const style = getComputedStyle(node);
      return { color: style.backgroundColor, image: style.backgroundImage };
    }));
    assert.ok(backgrounds.every((style) => style.color === "rgba(0, 0, 0, 0)" && style.image === "none"), JSON.stringify(backgrounds));
    if (detail) {
      const card = await page.getByRole("alert").evaluate((node) => ({ background: getComputedStyle(node).backgroundColor, color: getComputedStyle(node).color }));
      assert.notEqual(card.background, "rgba(0, 0, 0, 0)");
      assert.notEqual(card.color, card.background);
    }
    if (name === "pet") assert.equal(await page.locator(".pet-bubble span").textContent(), "角色回复保持可见");
    await page.screenshot({ path: resolve(output, `${name}.png`) });
    await qa("hide", id);
    await page.reload();
    if (detail) await page.getByRole("alert").waitFor();
    else await page.locator(".pet-surface").waitFor();
    let reloaded = await qa("snapshot", id);
    for (let attempt = 0; reloaded.readyCount <= after.readyCount && attempt < 100; attempt++) {
      await new Promise((done) => setTimeout(done, 50));
      reloaded = await qa("snapshot", id);
    }
    assert.ok(reloaded.readyCount > after.readyCount, "reload really reported ready again");
    assert.equal(reloaded.visible, false, `${name}: reload preserves hidden intent`);
    if (name === "pet") assert.equal(await page.locator(".pet-bubble span").textContent(), "角色回复保持可见");
    if (reloaded.alwaysOnTop !== alwaysOnTop) topmostFailures.push(`${name}: hidden reload`);
    await qa("show", id);
    const reshown = await qa("snapshot", id);
    assert.equal(reshown.visible, true, `${name}: explicit show after reload`);
    assert.equal(reshown.focused, false, `${name}: reshow does not steal focus`);
    assert.equal(reshown.events.includes("focus"), false, `${name}: no transient focus on reshow`);
    if (reshown.alwaysOnTop !== alwaysOnTop) topmostFailures.push(`${name}: reshow`);
    results[name] = { before, after, reloaded, reshown, backgrounds };
    await qa("destroy", id);
    if (name !== (builtRenderer ? "unregistered" : "mount")) await restart();
  }
  results.topmostFailures = topmostFailures;
  console.log(`PASS core (${builtRenderer ? "built file:// renderer" : "Vite renderer"}, ${fullscreenWitness ? "fullscreen" : "normal"} witness): real Electron paint gate, early show, no focus stealing, retained pet state, ${builtRenderer ? "two" : "four"} failure paths, topmost opt-out, transparent backgrounds, hidden reload`);
  // Preserve the native platform failure while still recording every core case.
  assert.deepEqual(topmostFailures, [], "native always-on-top state must be preserved");
} finally {
  releaseEntry();
  await writeFile(resolve(output, "results.json"), JSON.stringify(results, null, 2), "utf8");
  await writeFile(resolve(output, "electron.log"), log.join(""), "utf8");
  await app.close();
  await server.close();
}
