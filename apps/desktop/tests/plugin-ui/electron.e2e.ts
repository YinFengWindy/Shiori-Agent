import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { _electron } from "playwright";
import { build } from "vite";

await mkdir(".test-tmp-root", { recursive: true });
const output = await mkdtemp(resolve(".test-tmp-root", "plugin-ui-"));
for (const id of ["demo", "broken"]) {
  const directory = resolve(output, "plugins", id, "ui", "dist");
  await mkdir(directory, { recursive: true });
  await writeFile(resolve(directory, "style.css"), `.plugin-ui-qa { color: rgb(13, 27, 42); }`, "utf8");
  await writeFile(resolve(directory, "chunk.mjs"), `export const label = "Runtime hooks";`, "utf8");
  await writeFile(resolve(directory, "lazy.mjs"), `globalThis.pluginUiQaLazyVersion = 1; export default 1;`, "utf8");
  await writeFile(resolve(directory, "index.mjs"), id === "broken" ? "export default syntax is broken" : `
import React, { useState } from "react";
import { label } from "./chunk.mjs";
globalThis.pluginUiQaEvaluations = (globalThis.pluginUiQaEvaluations ?? 0) + 1;
export default { pluginId: "demo", navPage: { label, component: function Demo() {
  const [count, setCount] = useState(0);
  return React.createElement("button", { className: "plugin-ui-qa", onClick: () => setCount(count + 1) }, label + " " + count);
} } };`, "utf8");
}
await build({ configFile: false, root: resolve("apps/desktop/tests/plugin-ui"), base: "./", esbuild: { jsx: "automatic" }, build: { outDir: resolve(output, "renderer"), emptyOutDir: true } });
const app = await _electron.launch({
  executablePath: resolve("apps/desktop/node_modules/electron/dist/electron.exe"),
  args: [resolve("apps/desktop/tests/plugin-ui/bootstrap.cjs")],
  timeout: 30_000,
  env: { ...process.env, SHIORI_PLUGIN_UI_QA_ROOT: output },
});
try {
  const page = await app.firstWindow();
  page.setDefaultTimeout(15_000);
  page.on("console", (message) => { if (message.type() === "error") console.error(message.text()); });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.getByRole("button", { name: "Runtime hooks 0" }).waitFor();
  assert.equal(await page.evaluate(() => Reflect.get(globalThis, "pluginUiQaEvaluations")), 1);
  await page.getByRole("button").click();
  await page.getByRole("button", { name: "Runtime hooks 1" }).waitFor();
  assert.equal(await page.getByRole("button").evaluate((element) => getComputedStyle(element).color), "rgb(13, 27, 42)");
  const before = await page.evaluate(() => document.querySelector<HTMLLinkElement>('link[rel="stylesheet"]')!.href);
  const plugins = await page.evaluate(() => Reflect.get(globalThis, "refreshPluginUiQa")());
  assert.ok(plugins.find((plugin: { id: string; rendererError?: string }) => plugin.id === "broken")?.rendererError);
  await writeFile(resolve(output, "plugins", "demo", "ui", "dist", "lazy.mjs"), `globalThis.pluginUiQaLazyVersion = 2; export default 2;`, "utf8");
  const demo = plugins.find((plugin: { id: string }) => plugin.id === "demo");
  const modifiedLazyChunk = await page.evaluate(async (entry) => {
    try { await import(/* @vite-ignore */ new URL("lazy.mjs", entry).href); return false; } catch { return Reflect.get(globalThis, "pluginUiQaLazyVersion") === undefined; }
  }, demo.rendererUi.entry);
  assert.equal(modifiedLazyChunk, true);
  assert.equal(await page.evaluate(() => document.querySelector<HTMLLinkElement>('link[rel="stylesheet"]')!.href), before);
  await app.evaluate(() => { Reflect.set(globalThis, "pluginUiQaEnabled", false); });
  await page.evaluate(() => Reflect.get(globalThis, "refreshPluginUiQa")());
  await page.getByText("No plugin UI").waitFor();
  assert.equal(await page.locator('link[rel="stylesheet"]').count(), 0);
  await app.evaluate(() => { Reflect.set(globalThis, "pluginUiQaEnabled", true); });
  await page.evaluate(() => Reflect.get(globalThis, "refreshPluginUiQa")());
  await page.getByRole("button", { name: "Runtime hooks 0" }).waitFor();
  assert.equal(await page.evaluate(() => Reflect.get(globalThis, "pluginUiQaEvaluations")), 1);
  assert.equal(await page.evaluate(() => document.querySelector<HTMLLinkElement>('link[rel="stylesheet"]')!.href), before);
  const denied = await page.evaluate(async () => {
    try { await import(/* @vite-ignore */ "shiori-plugin://plugin/ungranted/outside.mjs"); return false; } catch { return true; }
  });
  assert.ok(denied);
  const csp = await page.evaluate(async () => {
    const violation = new Promise<string>((resolve) => document.addEventListener("securitypolicyviolation", (event) => resolve(event.effectiveDirective), { once: true }));
    let blocked = false;
    try { await import(/* @vite-ignore */ "data:text/javascript,globalThis.pluginUiCspEscaped=true"); } catch { blocked = true; }
    return { blocked, directive: await violation, executed: Reflect.get(globalThis, "pluginUiCspEscaped") === true };
  });
  assert.deepEqual(csp, { blocked: true, directive: "script-src-elem", executed: false });
  assert.deepEqual(errors, []);
  console.log("PASS: file renderer, shared React hooks, relative ESM chunk, changed lazy chunk rejected before first import, CSS, isolated syntax failure, stable repeated refresh, disable cleanup, reenable without ESM reevaluation, ungranted resource rejection, real CSP rejects data-module execution. ACTIVE roster is a fixture; workspace trust is not implemented by this test.");
} finally { await app.close(); }
