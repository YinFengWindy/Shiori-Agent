/// <reference types="node" />

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const hostSource = readFileSync(new URL("./host.ts", import.meta.url), "utf-8");
const ipcSource = readFileSync(new URL("./ipc.ts", import.meta.url), "utf-8");
const preloadSource = readFileSync(new URL("../pluginPreload.ts", import.meta.url), "utf-8");

describe("plugin desktop host security", () => {
  it("uses a separate sandboxed preload and denies child windows", () => {
    assert.match(hostSource, /sandbox:\s*true/);
    assert.match(hostSource, /contextIsolation:\s*true/);
    assert.match(hostSource, /nodeIntegration:\s*false/);
    assert.match(hostSource, /setWindowOpenHandler\(\(\) => \(\{ action: "deny" \}\)\)/);
  });

  it("infers plugin identity from the sender and exposes no desktop bridge", () => {
    assert.match(ipcSource, /host\.ownerFor\(event\.sender\)/);
    assert.doesNotMatch(ipcSource, /request\.plugin_id/);
    assert.match(preloadSource, /exposeInMainWorld\("shioriPlugin"/);
    assert.doesNotMatch(preloadSource, /desktop:invoke/);
  });
});
