import assert from "node:assert/strict";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { _electron } from "playwright";
import { PackagedApp, eventually } from "./packagedApp";
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

/** Use the unmodified development entry and real repository Python bridge. */
class DevelopmentApp extends PackagedApp {
  async launch() {
    const env: Record<string, string> = { SHIORI_DESKTOP_WORKSPACE: workspace, SHIORI_DESKTOP_USER_DATA_DIR: profile };
    for (const [key, value] of Object.entries(process.env)) if (value !== undefined && !(key in env)) env[key] = value;
    delete env.SHIORI_RENDERER_DEV_SERVER_URL;
    delete env.ELECTRON_RUN_AS_NODE;
    await access(this.paths.executable);
    this.app = await _electron.launch({ executablePath: this.paths.executable, args: [resolve(repository, "apps/desktop")], env, timeout: 45_000 });
    this.app.process().stderr?.on("data", (chunk: Buffer) => this.processErrors.push(chunk.toString("utf8")));
    const identity = await this.app.evaluate(({ app }) => ({ packaged: app.isPackaged, appPath: app.getAppPath(), profile: app.getPath("userData") }));
    assert.equal(identity.packaged, false);
    assert.equal(identity.appPath, resolve(repository, "apps/desktop"));
    assert.equal(identity.profile, profile);
    this.page = await eventually(async () => this.app!.windows().find((page) => page.url().endsWith("/index.html")), Boolean, "production development window");
    assert.ok(this.page);
    this.page.setDefaultTimeout(30_000);
    this.page.on("pageerror", (error) => this.errors.push(error.message));
    await Promise.race([this.page.locator(".app-frame").waitFor(), this.page.getByRole("button", { name: "跳过", exact: true }).waitFor()]);
    if (await this.page.getByRole("button", { name: "跳过", exact: true }).isVisible()) await this.page.getByRole("button", { name: "跳过", exact: true }).click();
    await this.page.locator(".app-frame").waitFor();
    await this.evidence.add("development-production-entry", identity);
  }
}

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
