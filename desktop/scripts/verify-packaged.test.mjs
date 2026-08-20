import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { verifyPackagedDesktop } from "./verify-packaged.mjs";

test("verifyPackagedDesktop accepts the required Windows release layout", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-packaged-layout-"));
  try {
    const files = [
      "resources/app.asar",
      "resources/runtime/shiori-runtime.exe",
      "resources/config.example.toml",
      "resources/assets/shiori-app-icon.ico",
      "resources/app.asar.unpacked/node_modules/uiohook-napi/prebuilds/win32-x64/uiohook-napi.node",
    ];
    for (const relativePath of files) {
      const path = join(root, relativePath);
      await mkdir(join(path, ".."), { recursive: true });
      await writeFile(path, "fixture");
    }

    await assert.doesNotReject(verifyPackagedDesktop(root));
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
