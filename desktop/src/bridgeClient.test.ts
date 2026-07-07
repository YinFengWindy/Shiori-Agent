/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { DesktopBridgeClient } from "./bridgeClient.js";

type MutableBridgeClient = {
  child: {
    stdin: {
      destroyed?: boolean;
      writable?: boolean;
      writableEnded?: boolean;
      write(chunk: string, callback?: (error?: Error | null) => void): boolean;
    };
    killed?: boolean;
    exitCode?: number | null;
  } | null;
  startPromise: Promise<void> | null;
};

describe("DesktopBridgeClient.invoke", () => {
  it("resolves with a bridge-exit error when the bridge disappears before stdin write", async () => {
    const client = new DesktopBridgeClient();
    const mutableClient = client as unknown as MutableBridgeClient;
    let writeCalled = false;

    mutableClient.child = {
      stdin: {
        writable: true,
        writableEnded: false,
        write() {
          writeCalled = true;
          return true;
        },
      },
      killed: false,
      exitCode: null,
    };
    mutableClient.startPromise = Promise.resolve();

    queueMicrotask(() => {
      mutableClient.child = null;
    });

    const response = await Promise.race([
      client.invoke({
        method: "health",
        payload: {},
      }),
      new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error("invoke timed out")), 250);
      }),
    ]);

    assert.equal(writeCalled, false);
    assert.equal(response.error?.code, "bridge_exit");
    assert.match(response.error?.message ?? "", /bridge/i);
  });
});
