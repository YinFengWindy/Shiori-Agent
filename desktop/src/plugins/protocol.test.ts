/// <reference types="node" />

import assert from "node:assert/strict";
import { mkdtemp, rm, symlink, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";
import { loadPluginResource, pluginResourceSchemePrivileges } from "./protocol";
import { PluginResourceRegistry } from "./resourceRegistry";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "shiori-plugin-protocol-"));
  temporaryDirectories.push(directory);
  return directory;
}

describe("plugin resource protocol", () => {
  it("serves only registered package files with a restrictive CSP", async () => {
    const root = await temporaryDirectory();
    await writeFile(join(root, "index.html"), "<main>plugin</main>", "utf-8");
    const registry = new PluginResourceRegistry();
    registry.replace([{ pluginId: "desktop-pet", packageDir: root }]);

    const response = await loadPluginResource(registry, "shiori-plugin://desktop-pet/index.html");
    const denied = await loadPluginResource(registry, "shiori-plugin://unknown/index.html");

    assert.equal(response.status, 200);
    assert.equal(await response.text(), "<main>plugin</main>");
    assert.match(response.headers.get("Content-Security-Policy") ?? "", /connect-src 'none'/);
    assert.equal(denied.status, 403);
    assert.deepEqual(pluginResourceSchemePrivileges, { standard: true, secure: true, supportFetchAPI: true });
  });

  it("rejects traversal and symlink escapes from the registered package", async (testContext) => {
    const root = await temporaryDirectory();
    const outside = await temporaryDirectory();
    const outsideFile = join(outside, "secret.js");
    const link = join(root, "linked.js");
    await writeFile(outsideFile, "secret", "utf-8");
    try {
      await symlink(outsideFile, link, "file");
    } catch (error) {
      if (["EPERM", "EACCES"].includes((error as NodeJS.ErrnoException).code ?? "")) {
        testContext.skip("file symlinks are unavailable in this Windows environment");
        return;
      }
      throw error;
    }
    const registry = new PluginResourceRegistry();
    registry.replace([{ pluginId: "desktop-pet", packageDir: root }]);

    const traversal = await loadPluginResource(registry, "shiori-plugin://desktop-pet/../secret.js");
    const escaped = await loadPluginResource(registry, "shiori-plugin://desktop-pet/linked.js");

    assert.notEqual(traversal.status, 200);
    assert.equal(escaped.status, 403);
    await unlink(link);
  });
});
