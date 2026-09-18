import assert from "node:assert/strict";
import { cp, readFile, rename, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { PackagedApp, eventually } from "./packagedApp";
import { activate, assertNoResidue, backendState, exercise } from "./packagedLifecycle";
import { hashFile, ownedPath } from "./packagedEvidence";

/** Invalid ZIP admission is visible before any fixture setup or partial activation. */
export async function invalidArchives(app: PackagedApp, fixture: string) {
  await app.settings();
  for (const variant of ["incompatible", "missing-entry"]) {
    await app.choose(resolve(fixture, `external_demo-1.0.0-${variant}.zip`));
    const expected = variant === "incompatible" ? /Host 2\.1\.0 does not satisfy >=99\.0\.0 <100\.0\.0/ : /backend.+plugin\.py/;
    const alert = app.page!.getByRole("alert").filter({ hasText: expected });
    await alert.waitFor();
    const diagnostic = await alert.innerText();
    assert.match(diagnostic, expected);
    assert.equal((await app.roster()).length, 0);
    assert.ok((await app.bridge("plugin.external_demo.inspect")).error);
    await app.screenshot(`invalid-${variant}`);
    await app.evidence.add(`invalid-${variant}-diagnostic`, diagnostic);
  }
}

/** Replace only a disposable artifact's resources and prove workspace ownership survives. */
export async function replaceResources(app: PackagedApp, sourceApp: string, application: string) {
  await app.close();
  const workspaceFile = resolve(app.paths.workspace, "plugins/external_demo/manifest.yaml");
  const privateFile = resolve(app.paths.workspace, "plugin-data/external_demo/kv.json");
  const preserved = { manifest: await hashFile(workspaceFile), data: await readFile(privateFile, "utf8") };
  const resources = ownedPath(application, "resources");
  const previous = ownedPath(application, "resources-previous");
  await rename(resources, previous);
  await cp(resolve(sourceApp, "../resources"), resources, { recursive: true, force: false, errorOnExist: true });
  assert.equal(await hashFile(workspaceFile), preserved.manifest);
  assert.equal(await readFile(privateFile, "utf8"), preserved.data);
  const resourceHash = await hashFile(resolve(resources, "app.asar"));
  await rm(previous, { recursive: true });
  await app.launch();
  await activate(app);
  await exercise(app, "2.0.0");
  assert.equal((await backendState(app)).saved, "retained-user-value");
  await app.evidence.add("replaced-packaged-resources-preserve-workspace-and-data", { resources, resourceHash, source: resolve(sourceApp, "../resources"), workspaceFile, manifestHash: preserved.manifest });
}

/** Duplicate discovery and a statically valid renderer failure roll back every entry. */
export async function activationFailures(app: PackagedApp, fixture: string) {
  await app.close();
  const duplicate = ownedPath(app.paths.workspace, "plugins/external_duplicate");
  await cp(resolve(fixture, "external_demo-2.0.0-valid"), duplicate, { recursive: true, errorOnExist: true, force: false });
  await app.launch();
  await app.settings();
  const conflicts = await app.state("CONFLICT");
  assert.equal(conflicts.length, 2);
  assert.ok(conflicts.every((row) => row.error || row.diagnostic));
  assert.ok((await app.bridge("plugin.external_demo.inspect")).error);
  assert.equal(await app.page!.getByRole("button", { name: "External lifecycle", exact: true }).count(), 0);
  assert.equal(app.app!.windows().filter((page) => page.url().includes("/surface.html")).length, 0);
  await app.screenshot("05-duplicate-diagnostic");
  await app.evidence.add("duplicate-id-no-partial-activation", conflicts);
  await app.close();
  await rm(duplicate, { recursive: true });
  await app.launch();
  await activate(app);
  await app.install(resolve(fixture, "external_demo-4.0.0-renderer-failure.zip"), { update: true });
  await app.restart();
  await app.settings();
  const failed = await eventually(() => app.roster(), (rows) => rows.some((row) => row.state === "FAILED"), "renderer rollback");
  assert.ok(JSON.stringify(failed).includes("intentional UI initialization failure"));
  // This failed activation need not have reached background setup. A retained
  // state from the prior version is not evidence that this attempt started.
  const backgroundState = JSON.parse(await readFile(resolve(app.paths.profile, "plugin-data/external_demo.json"), "utf8"));
  await assertNoResidue(app, backgroundState.version === "4.0.0");
  await app.screenshot("06-renderer-failure-diagnostic");
  await app.evidence.add("renderer-initialization-failure-rolls-back-entire-plugin", failed);
}
