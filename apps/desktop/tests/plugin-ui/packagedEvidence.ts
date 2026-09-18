import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";

/** Read JSON as an object and reject malformed evidence instead of hiding it. */
export function record(value: unknown): Record<string, unknown> {
  assert.ok(value !== null && typeof value === "object" && !Array.isArray(value));
  return value as Record<string, unknown>;
}

/** Hash artifacts without buffering the packaged runtime in memory. */
export async function hashFile(path: string) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

/** Restrict test mutations to their explicitly isolated output directory. */
export function ownedPath(root: string, ...parts: string[]) {
  const path = resolve(root, ...parts);
  const child = relative(root, path);
  assert.ok(child && !child.startsWith("..") && !isAbsolute(child), `Path escapes QA root: ${path}`);
  return path;
}

/** Persist step results immediately so interrupted acceptance remains diagnosable. */
export class Evidence {
  readonly steps: Array<{ name: string; detail: unknown; at: string }> = [];
  constructor(readonly output: string) {}
  async add(name: string, detail: unknown = {}) {
    this.steps.push({ name, detail, at: new Date().toISOString() });
    await writeFile(resolve(this.output, "results.json"), JSON.stringify({ automated: true, nativeFileChooser: "stubbed selection only; production picker staging and confirmation execute", manualAcceptance: "separate owner observation required", steps: this.steps }, null, 2), "utf8");
    console.log(`PASS ${name}`);
  }
}

/** Create a fresh isolated app copy, workspace and profile, without touching real user data. */
export async function preparePackagedRun(app: string, output: string) {
  await mkdir(output);
  const application = ownedPath(output, "application");
  await cp(dirname(app), application, { recursive: true, errorOnExist: true, force: false });
  const workspace = ownedPath(output, "workspace");
  const profile = ownedPath(output, "profile");
  await mkdir(workspace);
  await mkdir(profile);
  await writeFile(resolve(workspace, "config.toml"), '[llm]\nregistrations = []\n[agent.maintenance]\nmemory_optimizer_enabled = false\n[plugins.desktop_pet]\nenabled = false\n', "utf8");
  return { application, workspace, profile, executable: resolve(application, "Shiori.exe") };
}

/** Locate the one confirmed staging operation before deliberately corrupting that QA copy. */
export async function pendingPackage(workspace: string) {
  const root = resolve(workspace, "private_runtime/plugin-operations");
  const operations = await Promise.all((await readdir(root)).map(async (name) => ({
    root: resolve(root, name), journal: record(JSON.parse(await readFile(resolve(root, name, "operation.json"), "utf8"))),
  })));
  const pending = operations.filter(({ journal }) => journal.plugin_id === "external_demo" && journal.status === "pending");
  assert.equal(pending.length, 1);
  return pending[0];
}
