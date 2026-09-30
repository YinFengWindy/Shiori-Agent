import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  collectTrustedLocalAssetPaths,
  isLocalAssetInsideRoot,
  resolveLocalAssetCandidate,
} from "./localAssetPolicy.js";

test("Windows short paths share native asset identity and root containment", {
  skip: process.platform !== "win32",
}, async (context) => {
  const directory = await mkdtemp(join(tmpdir(), "shiori-asset-short-path-"));
  try {
    const imagePath = join(directory, "avatar.png");
    await writeFile(imagePath, "image", "utf-8");
    const shortPathResult = spawnSync("cmd.exe", [
      "/d", "/c", `for %I in ("${imagePath}") do @echo %~sI`,
    ], { encoding: "utf-8", windowsVerbatimArguments: true });
    assert.equal(shortPathResult.status, 0, shortPathResult.stderr);
    const shortPath = shortPathResult.stdout.trim();
    const canonicalPath = await realpath(imagePath);
    if (shortPath.toLowerCase() === canonicalPath.toLowerCase()) {
      context.skip("Windows short file names are unavailable on this volume");
      return;
    }

    assert.equal(resolveLocalAssetCandidate(shortPath)?.canonicalPath, canonicalPath);
    assert.equal(isLocalAssetInsideRoot(canonicalPath, join(shortPath, "..")), true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("pet package renderer assets are collected from trusted bridge payloads", () => {
  const previewPath = "C:\\workspace\\roles\\assets\\role-1\\pets\\pet-1\\preview.png";
  const spritesheetPath = "C:\\workspace\\roles\\assets\\role-1\\pets\\pet-1\\spritesheet.webp";

  const paths = collectTrustedLocalAssetPaths({
    pet_packages: [{
      preview_abs: previewPath,
      spritesheet_abs: spritesheetPath,
    }],
  });

  assert.deepEqual(paths, [previewPath, spritesheetPath]);
});

test("cached channel avatars are collected from phone and identity payloads", () => {
  const senderPath = "C:\\workspace\\private_runtime\\channel-avatars\\sender\\qq_42-1a2b3c4d.png";
  const chatPath = "C:\\workspace\\private_runtime\\channel-avatars\\chat\\qq_gqq_5-1a2b3c4d.png";

  const paths = collectTrustedLocalAssetPaths({
    conversation: { avatar_abs: chatPath },
    messages: [{ sender_avatar_abs: senderPath }, { sender_avatar_abs: null }],
    identities: [{ avatar_abs: senderPath }],
  });

  assert.deepEqual(paths, [chatPath, senderPath, senderPath]);
});
