/** Install the actual npm tarball outside the checkout and exercise every entry. */
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, writeFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { parseArgs } from "node:util";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const { values } = parseArgs({ options: { tarball: { type: "string" } } });
const output = await mkdtemp(join(tmpdir(), "shiori-sdk-npm-"));
const pnpmScript = process.env.npm_execpath;
if (!pnpmScript) throw new Error("Run this artifact probe with pnpm run sdk:smoke");
function run(args, cwd) {
  execFileSync(process.execPath, [pnpmScript, ...args], { cwd, stdio: "inherit" });
}
let tarball = values.tarball && resolve(values.tarball);
if (!tarball) {
  run(["--filter", "@yinfengwindy/shiori-sdk", "pack", "--pack-destination", output], root);
  const name = (await readdir(output)).find((name) => name.endsWith(".tgz"));
  if (!name) throw new Error("SDK tarball was not produced");
  tarball = join(output, name);
}
await writeFile(join(output, "package.json"), '{"name":"sdk-consumer","private":true,"type":"module"}\n', "utf8");
run(["add", tarball, "react@19.2.8", "react-dom@19.2.8", "typescript@5.9.3", "@types/react@19", "@types/node@26.6.3"], output);
const source = JSON.parse(await readFile(join(root, "packages/sdk/package.json"), "utf8"));
await writeFile(join(output, "smoke.mjs"), `
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { BridgeError, errorMessage, usePrivateAutosave } from "@yinfengwindy/shiori-sdk";
import * as contract from "@yinfengwindy/shiori-sdk/contract";
import * as host from "@yinfengwindy/shiori-sdk/host-internal";
import { deferred, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createElement } from "react";
const manifest = JSON.parse(await readFile("node_modules/@yinfengwindy/shiori-sdk/package.json", "utf8"));
assert.equal(manifest.version, ${JSON.stringify(source.version)});
assert.ok(import.meta.resolve("@yinfengwindy/shiori-sdk").includes("/dist/index.js"));
assert.equal(typeof BridgeError, "function");
assert.equal(errorMessage(new Error("probe")), "probe");
assert.equal(typeof createFakePluginClient, "function");
assert.equal(typeof host, "object");
assert.equal(typeof contract, "object");
const task = deferred(); task.resolve("ready"); assert.equal(await task.promise, "ready");
const mounted = await mountTestComponent(createElement("button", null, "standalone"));
try { assert.match(mounted.container.textContent, /standalone/); } finally { await mounted.cleanup(); }
const client = createFakePluginClient();
function PrivateDocument() {
  const state = usePrivateAutosave(client, "settings", { load: async () => ({ value: "private SDK draft" }), save: async (value) => value });
  return createElement("output", null, state.draft?.value);
}
const document = await mountTestComponent(createElement(PrivateDocument));
try { assert.equal(document.container.textContent, "private SDK draft"); } finally { await document.cleanup(); }
console.log("Non-editable npm SDK import + DOM testing smoke passed", manifest.version);
`, "utf8");
execFileSync(process.execPath, ["smoke.mjs"], { cwd: output, stdio: "inherit" });
await writeFile(join(output, "consumer.ts"), `
import { type PluginRpcClient, usePrivateAutosave } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
const client: PluginRpcClient = createFakePluginClient();
void client;
void usePrivateAutosave;
`, "utf8");
run(["exec", "tsc", "--noEmit", "--strict", "--target", "ES2022", "--module", "ESNext", "--moduleResolution", "bundler", "consumer.ts"], output);
console.log(`SDK npm artifact evidence: ${output}`);
