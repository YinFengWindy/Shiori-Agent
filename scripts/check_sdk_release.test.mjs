import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import { checkSdkRelease } from "./check_sdk_release.mjs";

const sourcePath = "packages/sdk/python/shiori_sdk/api.py";

function repository(t) {
  const root = mkdtempSync(join(tmpdir(), "shiori-sdk-release-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: "pipe" }).trim();
  const write = (path, text) => {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text, "utf8");
  };
  const version = (value) => {
    write("packages/sdk/python/shiori_sdk/_version.py", `__version__ = "${value}"\n`);
    write("packages/sdk/package.json", JSON.stringify({ name: "sdk", version: value }));
    write("setup.py", `setup(install_requires=["shiori-sdk==${value}"])\n`);
    write("packages/shiori-host-testing/pyproject.toml", `dependencies = ["shiori-sdk[testing]==${value}"]\n`);
  };
  const commit = () => {
    git("add", ".");
    git("commit", "--allow-empty", "-m", "fixture");
    return git("rev-parse", "HEAD");
  };
  git("init");
  git("config", "user.email", "sdk-test@example.invalid");
  git("config", "user.name", "SDK Release Test");
  git("config", "commit.gpgsign", "false");
  git("config", "core.autocrlf", "false");
  write(sourcePath, "def contract():\n    return 1\n");
  write("packages/sdk/src/index.ts", "export const contract = 1;\n");
  version("3.1.1");
  commit();
  return { root, git, write, version, commit };
}

test("a finalized first SDK release passes without published source history", async (t) => {
  const repo = repository(t);
  assert.deepEqual(await checkSdkRelease(repo.root), { version: "3.1.1", checked: 0 });
});

test("all exact consumers must agree with the Python version before release", async (t) => {
  const repo = repository(t);
  for (const [path, content] of [
    ["packages/sdk/package.json", '{"version":"3.1.0"}'],
    ["setup.py", 'setup(install_requires=["shiori-sdk==3.1.0"])'],
    ["packages/shiori-host-testing/pyproject.toml", 'dependencies = ["shiori-sdk[testing]==3.1.0"]'],
    ["packages/sdk/python/shiori_sdk/_version.py", '__version__ = "3.1.0"\n'],
  ]) {
    repo.version("3.1.1");
    repo.write(path, content);
    await assert.rejects(checkSdkRelease(repo.root), /versions differ/);
  }
});

test("an SDK tag freezes both Python and renderer source", async (t) => {
  const repo = repository(t);
  repo.git("tag", "-a", "sdk-v3.1.1", "-m", "published");
  assert.equal((await checkSdkRelease(repo.root)).checked, 1);
  repo.write(sourcePath, "def contract():\n    return 2\n");
  await assert.rejects(checkSdkRelease(repo.root), /source differs from sdk-v3.1.1/);
  repo.git("restore", sourcePath);
  repo.write("packages/sdk/src/index.ts", "export const contract = 2;\n");
  await assert.rejects(checkSdkRelease(repo.root), /source differs from sdk-v3.1.1/);
});

test("a desktop tag freezes its SDK even before a registry SDK tag exists", async (t) => {
  const repo = repository(t);
  repo.git("tag", "v0.5.5");
  assert.equal((await checkSdkRelease(repo.root)).checked, 1);
  repo.write(sourcePath, "def contract():\n    return 2\n");
  await assert.rejects(checkSdkRelease(repo.root), /source differs from v0.5.5/);
});

test("a new version passes with its own HEAD tag; an unchanged retry also passes", async (t) => {
  const repo = repository(t);
  repo.git("tag", "v0.5.5");
  repo.write(sourcePath, "def contract():\n    return 2\n");
  repo.version("3.1.2");
  assert.deepEqual(await checkSdkRelease(repo.root), { version: "3.1.2", checked: 0 });
  repo.commit();
  repo.git("tag", "sdk-v3.1.2");
  repo.git("tag", "v0.5.6");
  assert.deepEqual(await checkSdkRelease(repo.root), { version: "3.1.2", checked: 2 });
});

test("a new HEAD SDK tag cannot hide an earlier conflicting desktop distribution", async (t) => {
  const repo = repository(t);
  repo.git("tag", "v0.5.5");
  repo.write(sourcePath, "def contract():\n    return 2\n");
  repo.commit();
  repo.git("tag", "sdk-v3.1.1");
  await assert.rejects(checkSdkRelease(repo.root), /source differs from v0.5.5/);
});

test("the original SDK tag cannot be ignored in favor of a newer desktop tag", async (t) => {
  const repo = repository(t);
  repo.git("tag", "sdk-v3.1.1");
  repo.write(sourcePath, "def contract():\n    return 2\n");
  repo.commit();
  repo.git("tag", "v0.5.5");
  await assert.rejects(checkSdkRelease(repo.root), /source differs from sdk-v3.1.1/);
});

test("version rollback is rejected even when the released source was on another branch", async (t) => {
  const repo = repository(t);
  const before = repo.git("rev-parse", "HEAD");
  repo.version("3.2.0");
  repo.commit();
  repo.git("tag", "v0.5.6");
  repo.git("checkout", "--detach", before);
  await assert.rejects(checkSdkRelease(repo.root), /would roll back 3.2.0 already distributed by v0.5.6/);
});

test("README and actual tests may change, while public testing helpers and packaging may not", async (t) => {
  const repo = repository(t);
  repo.git("tag", "sdk-v3.1.1");
  repo.write("packages/sdk/README.md", "Updated guide\n");
  repo.write("packages/sdk/tests/test_api.py", "def test_contract(): pass\n");
  repo.write("packages/sdk/src/index.test.ts", "// Regression test\n");
  assert.equal((await checkSdkRelease(repo.root)).checked, 1);
  for (const path of ["packages/sdk/src/testing/fakes.ts", "packages/sdk/python/shiori_sdk/testing/fakes.py", "packages/sdk/scripts/build.mjs", "packages/sdk/pyproject.toml"]) {
    repo.write(path, "changed\n");
    await assert.rejects(checkSdkRelease(repo.root), /source differs/);
    rmSync(join(repo.root, path));
  }
});

test("deleting published source is a contract change", async (t) => {
  const repo = repository(t);
  repo.git("tag", "v0.5.5");
  rmSync(join(repo.root, sourcePath));
  await assert.rejects(checkSdkRelease(repo.root), /source differs from v0.5.5/);
});

test("Git's CRLF normalization avoids false differences on Windows", async (t) => {
  const repo = repository(t);
  repo.git("config", "core.autocrlf", "true");
  repo.git("tag", "sdk-v3.1.1");
  repo.write(sourcePath, readFileSync(join(repo.root, sourcePath), "utf8").replace(/\n/g, "\r\n"));
  assert.equal((await checkSdkRelease(repo.root)).checked, 1);
});

test("malformed SDK tags and missing version sources fail closed", async (t) => {
  const repo = repository(t);
  repo.git("tag", "sdk-v3.1.0");
  await assert.rejects(checkSdkRelease(repo.root), /does not match its SDK source version/);
  repo.git("tag", "-d", "sdk-v3.1.0");
  repo.git("rm", "packages/sdk/python/shiori_sdk/_version.py");
  repo.commit();
  repo.git("tag", "v0.5.5");
  repo.version("3.1.2");
  await assert.rejects(checkSdkRelease(repo.root), /SDK version source missing from v0.5.5/);
});

test("desktop history from before the unified SDK is explicitly skipped", async (t) => {
  const repo = repository(t);
  repo.git("rm", "-r", "packages/sdk");
  repo.commit();
  repo.git("tag", "v0.2.0");
  repo.version("3.1.2");
  assert.deepEqual(await checkSdkRelease(repo.root), { version: "3.1.2", checked: 0 });
});

test("a shallow clone cannot skip published history", async (t) => {
  const repo = repository(t);
  const shallow = mkdtempSync(join(tmpdir(), "shiori-sdk-shallow-"));
  t.after(() => rmSync(shallow, { recursive: true, force: true }));
  execFileSync("git", ["clone", "--depth=1", pathToFileURL(repo.root).href, shallow], { stdio: "pipe" });
  await assert.rejects(checkSdkRelease(shallow), /complete Git history and tags/);
});

test("refreshing tags before distribution catches an SDK published during the build", async (t) => {
  const origin = repository(t);
  const checkout = mkdtempSync(join(tmpdir(), "shiori-sdk-build-"));
  t.after(() => rmSync(checkout, { recursive: true, force: true }));
  execFileSync("git", ["clone", origin.root, checkout], { stdio: "pipe" });
  const git = (...args) => execFileSync("git", args, { cwd: checkout, encoding: "utf8", stdio: "pipe" }).trim();
  const pinned = git("rev-parse", "HEAD");
  assert.equal((await checkSdkRelease(checkout)).checked, 0);
  origin.write(sourcePath, "def contract():\n    return 2\n");
  origin.commit();
  origin.git("tag", "sdk-v3.1.1");
  git("fetch", "--tags", "origin");
  assert.equal(git("rev-parse", "HEAD"), pinned);
  await assert.rejects(checkSdkRelease(checkout), /source differs from sdk-v3.1.1/);
});
