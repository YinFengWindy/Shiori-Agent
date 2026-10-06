import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { DevelopmentApp } from "./packagedDevelopmentApp";
import { Evidence } from "./packagedEvidence";
import { lifecycle } from "./packagedLifecycle";
import { buildDistributionFixture } from "./distributionFixture";

const repository = resolve(import.meta.dirname, "../../../..");
await mkdir(resolve(repository, ".test-tmp-root"), { recursive: true });
const output = await mkdtemp(resolve(repository, ".test-tmp-root/distribution-"));
const source = resolve(repository, "plugins/external_demo");
const workspace = resolve(output, "workspace"), profile = resolve(output, "profile");
await mkdir(workspace);
await mkdir(profile);
await writeFile(resolve(workspace, "config.toml"), '[llm]\nregistrations = []\n[agent.maintenance]\nmemory_optimizer_enabled = false\n[plugins.desktop_pet]\nenabled = false\n', "utf8");

const evidence = new Evidence(output);
const app = new DevelopmentApp({ workspace, profile, executable: resolve(repository, "apps/desktop/node_modules/electron/dist/electron.exe") }, evidence, "development");
let ownsSource = false;
try {
  // Exclusive creation prevents replacing or cleaning up an existing user plugin.
  await mkdir(source);
  ownsSource = true;
  await buildDistributionFixture(repository, source, output);
  await app.launch();
  assert.equal((await app.roster()).length, 0, "external source appeared as a builtin candidate");
  await lifecycle(app, output);
  assert.deepEqual(app.errors, []);
  await evidence.add("complete", { sourceStillPresent: Boolean(await readFile(resolve(source, "manifest.yaml"), "utf8")), developmentRuntime: true, frozenRuntime: false });
} catch (error) {
  if (app.page) await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8");
  await writeFile(resolve(output, "failure.txt"), String(error instanceof Error ? error.stack : error), "utf8");
  throw error;
} finally {
  await app.close();
  await writeFile(resolve(output, "process-stderr.log"), app.processErrors.join(""), "utf8");
  if (ownsSource) await rm(source, { recursive: true, force: true });
}
console.log(`PASS external source distribution lifecycle. Evidence: ${output}`);
