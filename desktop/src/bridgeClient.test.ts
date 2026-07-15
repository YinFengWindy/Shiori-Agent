/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { DesktopBridgeClient } from "./bridgeClient.js";

type PendingResolver = (response: BridgeResponse) => void;

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
  pending: Map<string, PendingResolver>;
  invokeTimeoutMs(method: string): number;
};

type BridgeResponse = Awaited<ReturnType<DesktopBridgeClient["invoke"]>>;

function createReadyClient(
  onWrite: (request: { id: string; method: string }) => void,
  timeoutMs = 20,
): { client: DesktopBridgeClient; mutableClient: MutableBridgeClient } {
  const client = new DesktopBridgeClient();
  const mutableClient = client as unknown as MutableBridgeClient;
  mutableClient.child = {
    stdin: {
      writable: true,
      writableEnded: false,
      write(chunk) {
        onWrite(JSON.parse(chunk) as { id: string; method: string });
        return true;
      },
    },
    killed: false,
    exitCode: null,
  };
  mutableClient.startPromise = Promise.resolve();
  mutableClient.invokeTimeoutMs = () => timeoutMs;
  return { client, mutableClient };
}

describe("DesktopBridgeClient.invoke", () => {
  it("uses short health, default, and extended image generation timeouts", () => {
    const client = new DesktopBridgeClient() as unknown as MutableBridgeClient;

    assert.equal(client.invokeTimeoutMs("health"), 5_000);
    assert.equal(client.invokeTimeoutMs("roles.list"), 30_000);
    assert.equal(client.invokeTimeoutMs("novelai.generate"), 5 * 60_000);
  });

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

  it("clears the timeout and pending entry when the bridge responds", async () => {
    const { client, mutableClient } = createReadyClient((request) => {
      queueMicrotask(() => {
        mutableClient.pending.get(request.id)?.({
          id: request.id,
          type: "response",
          method: request.method,
          payload: { ok: true },
          error: undefined,
        });
      });
    });

    const response = await client.invoke({ method: "roles.list", payload: {} });

    assert.deepEqual(response.payload, { ok: true });
    assert.equal(response.error, undefined);
    assert.equal(mutableClient.pending.size, 0);
  });

  it("returns a structured error and clears pending when the bridge never responds", async () => {
    let requestId = "";
    const { client, mutableClient } = createReadyClient((request) => {
      requestId = request.id;
    });

    const response = await client.invoke({ method: "roles.list", payload: {} });

    assert.equal(response.id, requestId);
    assert.equal(response.method, "roles.list");
    assert.equal(response.error?.code, "bridge_timeout");
    assert.match(response.error?.message ?? "", /20ms/);
    assert.equal(mutableClient.pending.has(requestId), false);
    assert.equal(client.isRunning(), true);
  });

  it("ignores a late response after timeout without affecting the next request", async () => {
    const requestIds: string[] = [];
    const { client, mutableClient } = createReadyClient((request) => {
      requestIds.push(request.id);
      if (requestIds.length === 2) {
        queueMicrotask(() => {
          mutableClient.pending.get(requestIds[0])?.({
            id: requestIds[0],
            type: "response",
            method: "roles.list",
            payload: { stale: true },
            error: undefined,
          });
          mutableClient.pending.get(request.id)?.({
            id: request.id,
            type: "response",
            method: request.method,
            payload: { current: true },
            error: undefined,
          });
        });
      }
    });

    const timedOut = await client.invoke({ method: "roles.list", payload: {} });
    const current = await client.invoke({ method: "roles.list", payload: {} });

    assert.equal(timedOut.error?.code, "bridge_timeout");
    assert.deepEqual(current.payload, { current: true });
    assert.equal(mutableClient.pending.size, 0);
  });
});
