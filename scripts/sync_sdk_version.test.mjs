import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { syncSdkVersion } from "./sync_sdk_version.mjs";

async function fixture(t, { npm = "3.1.3", host = "3.1.2", testing = "3.1.3" } = {}) {
  const root = await mkdtemp(join(tmpdir(), "shiori-sdk-versions-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const files = {
    "packages/sdk/python/shiori_sdk/_version.py": '__version__ = "3.1.3"\nRUNTIME_API_VERSION = __version__\n',
    "packages/sdk/package.json": JSON.stringify({ name: "sdk", version: npm }),
    "setup.py": `setup(install_requires=["httpx>=0.28", "shiori-sdk==${host}", "shiori-plugin-default-memory==0.1.0"])\n`,
    "packages/shiori-host-testing/pyproject.toml": `[project]\nversion = "0.1.0"\ndependencies = ["shiori-agent==0.1.0", "shiori-sdk[testing]==${testing}"]\n`,
  };
  for (const [name, value] of Object.entries(files)) {
    await mkdir(dirname(join(root, name)), { recursive: true });
    await writeFile(join(root, name), value, "utf8");
  }
  return { root, files };
}

test("check rejects the actual stale host pin even when npm and SDK already match", async (t) => {
  const { root, files } = await fixture(t);
  await assert.rejects(syncSdkVersion(root, { check: true }), /setup\.py \(3\.1\.2\)/);
  for (const [name, value] of Object.entries(files)) assert.equal(await readFile(join(root, name), "utf8"), value, "check must be read-only");
  await syncSdkVersion(root);
  assert.equal(await readFile(join(root, "setup.py"), "utf8"), files["setup.py"].replace("shiori-sdk==3.1.2", "shiori-sdk==3.1.3"));
  await assert.doesNotReject(syncSdkVersion(root, { check: true }));
});

test("synchronization updates npm and both exact Python pins without changing independent package versions", async (t) => {
  const { root, files } = await fixture(t, { npm: "3.1.1", host: "3.1.1", testing: "3.1.1" });
  await assert.rejects(syncSdkVersion(root, { check: true }), /packages\/shiori-host-testing\/pyproject\.toml/);
  assert.equal(await syncSdkVersion(root), "3.1.3");
  assert.equal(JSON.parse(await readFile(join(root, "packages/sdk/package.json"), "utf8")).version, "3.1.3");
  assert.equal(await readFile(join(root, "packages/shiori-host-testing/pyproject.toml"), "utf8"), files["packages/shiori-host-testing/pyproject.toml"].replace("shiori-sdk[testing]==3.1.1", "shiori-sdk[testing]==3.1.3"));
  await assert.doesNotReject(syncSdkVersion(root, { check: true }));
});

test("an unrecognized host declaration fails before any other metadata is rewritten", async (t) => {
  const { root, files } = await fixture(t, { npm: "3.1.1" });
  await writeFile(join(root, "setup.py"), 'setup(install_requires=["shiori-sdk>=4.0"])\n', "utf8");
  await assert.rejects(syncSdkVersion(root), /Expected exactly one SDK version pin in setup\.py/);
  assert.equal(await readFile(join(root, "packages/sdk/package.json"), "utf8"), files["packages/sdk/package.json"]);
});
