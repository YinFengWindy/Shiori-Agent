import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { createReleaseGit } from "./daily-release-git.mjs";
import { releaseRepository } from "./daily-release-test-fixtures.mjs";

test("refresh obtains main history and peels annotated stable tags", (t) => {
  const repo = releaseRepository(t);
  const base = repo.git.resolve("HEAD");
  const head = repo.commit();
  repo.git.refresh();
  assert.equal(repo.git.resolve("origin/main"), head);
  assert.equal(repo.git.tags().get("v0.5.0"), base);
  assert.equal(repo.git.count(base, head), 1);
});

test("shallow checkout is rejected before fetching and counting incomplete history", (t) => {
  const repo = releaseRepository(t);
  repo.commit();
  const shallow = mkdtempSync(join(tmpdir(), "shiori-shallow-"));
  t.after(() => rmSync(shallow, { recursive: true, force: true }));
  execFileSync("git", ["clone", "--depth=1", pathToFileURL(repo.directory).href, shallow], { stdio: "pipe" });
  assert.throws(() => createReleaseGit(shallow).refresh(), /complete Git history/);
});

test("a remote tag deletion cannot leave a stale local successful baseline", (t) => {
  const origin = releaseRepository(t);
  const checkout = mkdtempSync(join(tmpdir(), "shiori-release-clone-"));
  t.after(() => rmSync(checkout, { recursive: true, force: true }));
  execFileSync("git", ["clone", origin.directory, checkout], { stdio: "pipe" });
  const git = createReleaseGit(checkout);
  assert.ok(git.tags().has("v0.5.0"));
  origin.run("tag", "-d", "v0.5.0");
  git.refresh();
  assert.ok(git.resolve("v0.5.0"));
  assert.equal(git.tags().has("v0.5.0"), false);
});
