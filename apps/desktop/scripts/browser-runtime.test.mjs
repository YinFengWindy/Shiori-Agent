import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { prepareBrowserRuntime } from "./browser-runtime.mjs";

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "shiori-browser-runtime-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const plugin = join(root, "plugins", "browser_use");
  await mkdir(plugin, { recursive: true });
  const contents = { binary: Buffer.from("fixed binary"), chrome: Buffer.from("fixed zip") };
  const manifest = Object.fromEntries([["agentBrowser", "binary"], ["chrome", "chrome"]].map(([key, name]) => [key, {
    version: "1.0", url: `https://example.test/${name}`, sha256: createHash("sha256").update(contents[name]).digest("hex"),
  }]));
  await writeFile(join(plugin, "native-runtime.json"), JSON.stringify(manifest));
  await writeFile(join(plugin, "LICENSE.agent-browser"), "license");
  const downloads = [];
  const download = async (url) => {
    downloads.push(url);
    return new Response(contents[url.split("/").at(-1)]);
  };
  const extract = async (_archive, destination) => {
    await mkdir(join(destination, "chrome-win64"), { recursive: true });
    await writeFile(join(destination, "chrome-win64", "chrome.exe"), "chrome");
    await writeFile(join(destination, "chrome-win64", "ABOUT"), "Chrome license notice");
  };
  return { repositoryRoot: root, targetPlatform: "win32", download, extract, downloads };
}

test("prepares and reuses checksum-verified artifacts and licensing in frozen layout", async (t) => {
  const options = await fixture(t);
  const output = await prepareBrowserRuntime(options);
  assert.equal(output, join(options.repositoryRoot, "native", "browser-use"));
  assert.equal(await readFile(join(output, "LICENSE.agent-browser"), "utf8"), "license");
  assert.equal(await readFile(join(output, "chrome-win64", "ABOUT"), "utf8"), "Chrome license notice");
  await prepareBrowserRuntime(options);
  assert.equal(options.downloads.length, 2);
});

test("rejects checksum failure without installing an untrusted binary", async (t) => {
  const options = await fixture(t);
  await assert.rejects(prepareBrowserRuntime({ ...options, download: async () => new Response("wrong") }), /SHA256 mismatch/);
  await assert.rejects(readFile(join(options.repositoryRoot, "native", "browser-use", "agent-browser.exe")), /ENOENT/);
});

test("does not download or launch Windows artifacts in ordinary Linux checks", async () => {
  await assert.rejects(prepareBrowserRuntime({ repositoryRoot: "/unused", targetPlatform: "linux", download: () => { throw new Error("should not download"); } }), /requires Windows/);
});
