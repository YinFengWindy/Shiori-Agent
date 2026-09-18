import assert from "node:assert/strict";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { PackagedApp } from "./packagedApp";
import { Evidence, hashFile, preparePackagedRun } from "./packagedEvidence";
import { lifecycle } from "./packagedLifecycle";
import { activationFailures, invalidArchives, replaceResources } from "./packagedFailures";

const { values } = parseArgs({ options: {
  app: { type: "string" }, fixture: { type: "string" }, output: { type: "string" }, version: { type: "string", default: "0.3.0-rc.1" },
} });
assert.equal(process.platform, "win32", "Windows packaged acceptance only");
assert.ok(values.app && values.fixture && values.output, "--app, --fixture and a fresh --output are required");
const sourceApp = resolve(values.app);
const fixture = resolve(values.fixture);
const output = resolve(values.output);
const paths = await preparePackagedRun(sourceApp, output);
const evidence = new Evidence(output);
const archives = await Promise.all((await readdir(fixture)).filter((name) => name.endsWith(".zip")).map(async (name) => ({ name, sha256: await hashFile(resolve(fixture, name)) })));
await evidence.add("artifacts", { sourceApp, appHash: await hashFile(sourceApp), asarHash: await hashFile(resolve(sourceApp, "../resources/app.asar")), runtimeHash: await hashFile(resolve(sourceApp, "../resources/runtime/shiori-runtime.exe")), fixture, archives, paths, node: process.version, architecture: process.arch });
const app = new PackagedApp(paths, evidence, values.version);
try {
  await app.launch();
  await invalidArchives(app, fixture);
  await lifecycle(app, fixture);
  await replaceResources(app, sourceApp, paths.application);
  await activationFailures(app, fixture);
  await evidence.add("complete", { rendererErrors: app.errors, automation: "real app.isPackaged production entry; chooser result substituted", manual: "not represented by this automated run" });
} catch (error) {
  if (app.page) {
    await app.screenshot("failure");
    await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8");
  }
  await writeFile(resolve(output, "failure.txt"), String(error instanceof Error ? error.stack : error), "utf8");
  throw error;
} finally {
  await app.close();
  await writeFile(resolve(output, "renderer-errors.json"), JSON.stringify(app.errors, null, 2), "utf8");
  await writeFile(resolve(output, "process-stderr.log"), app.processErrors.join(""), "utf8");
}
assert.ok((await readFile(resolve(output, "results.json"), "utf8")).includes('"complete"'));
console.log(`PASS packaged lifecycle. Evidence: ${output}`);
