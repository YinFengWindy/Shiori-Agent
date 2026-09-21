import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { prepareComputerRuntime } from "./computer-runtime.mjs";
import { digest } from "./native-runtime.mjs";

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), "shiori-computer-runtime-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const plugin = join(root, "plugins", "computer_use");
  await mkdir(plugin, { recursive: true });
  const binary = Buffer.from("fixed driver"), helper = Buffer.from("fixed uia"), archive = Buffer.from("fixed archive");
  const manifest = { driver: { version: "0.28.2", url: "https://example.test/driver.zip", sha256: digest(archive) },
    files: { "cua-driver.exe": digest(binary), "cua-driver-uia.exe": digest(helper) } };
  await writeFile(join(plugin, "native-runtime.json"), JSON.stringify(manifest));
  await writeFile(join(plugin, "LICENSE.cua-driver"), "MIT License");
  const downloads = [];
  const download = async (url) => { downloads.push(url); return new Response(archive); };
  const extract = async (_archive, destination) => {
    await writeFile(join(destination, "cua-driver.exe"), binary);
    await writeFile(join(destination, "cua-driver-uia.exe"), helper);
    await writeFile(join(destination, "unneeded.dll"), "unused SDK");
  };
  return { repositoryRoot: root, targetPlatform: "win32", targetArch: "x64", download, extract, downloads };
}

test("prepares fixed binaries with source/license metadata and repairs modified components", async (t) => {
  const options = await fixture(t);
  const output = await prepareComputerRuntime(options);
  assert.equal(await readFile(join(output, "LICENSE.cua-driver"), "utf8"), "MIT License");
  await assert.rejects(readFile(join(output, "unneeded.dll")), /ENOENT/);
  await writeFile(join(output, "cua-driver-uia.exe"), "corrupted");
  await prepareComputerRuntime(options);
  assert.equal(await readFile(join(output, "cua-driver-uia.exe"), "utf8"), "fixed uia");
  assert.equal(options.downloads.length, 1);
});

test("rejects archive checksum mismatch and incomplete extraction", async (t) => {
  const options = await fixture(t);
  await assert.rejects(prepareComputerRuntime({ ...options, download: async () => new Response("wrong") }), /SHA256 mismatch/);
  await assert.rejects(prepareComputerRuntime({ ...options, extract: async () => {} }), /ENOENT/);
  await assert.rejects(readFile(join(options.repositoryRoot, "native", "computer-use", "cua-driver.exe")), /ENOENT/);
});

test("rejects unsupported platform and architecture before downloading", async () => {
  for (const [targetPlatform, targetArch] of [["linux", "x64"], ["win32", "arm64"]]) {
    await assert.rejects(prepareComputerRuntime({ repositoryRoot: "/unused", targetPlatform, targetArch }), /requires Windows x64/);
  }
});
