/// <reference types="node" />

import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { describe, it } from "node:test";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import type { BridgeResponse } from "./shared.js";
import { DesktopBridgeClient } from "./bridgeClient.js";

const bridgeCommand = {
  executable: "C:/runtime/shiori-runtime.exe",
  args: ["bridge"],
  cwd: "C:/runtime",
};

type PendingRequest = {
  id: string;
  method: string;
  resolve(response: BridgeResponse): void;
};

type TestSession = {
  child: FakeChild;
  pending: Map<string, PendingRequest>;
  stderrChunks: string[];
  stdoutBuffer: string;
  startPromise: Promise<void>;
  stopPromise: Promise<void> | null;
  writeTail: Promise<void>;
  stopRequested: boolean;
  exited: boolean;
  exitEmitted: boolean;
  exitPromise: Promise<void>;
  resolveExit(): void;
};

type MutableBridgeClient = {
  session: TestSession | null;
  createSession(child: ChildProcessWithoutNullStreams): TestSession;
  attachSessionListeners(session: TestSession): void;
  invokeTimeoutMs(method: string, requestedTimeoutMs?: number): number | null;
  gracefulStopTimeoutMs(): number;
  forcedStopTimeoutMs(): number;
  killProcessTree(pid: number): void;
};

class FakeStdin extends EventEmitter {
  destroyed = false;
  writable = true;
  writableEnded = false;
  readonly writes: string[] = [];
  onWrite: (chunk: string, callback: (error?: Error | null) => void) => void = (
    _chunk,
    callback,
  ) => callback();
  onEnd: () => void = () => undefined;

  write(chunk: string, callback: (error?: Error | null) => void): boolean {
    this.writes.push(chunk);
    this.onWrite(chunk, callback);
    return true;
  }

  end(): void {
    this.writableEnded = true;
    this.onEnd();
  }
}

class FakeChild extends EventEmitter {
  readonly stdin = new FakeStdin();
  readonly stdout = new EventEmitter();
  readonly stderr = new EventEmitter();
  pid = 1234;
  killed = false;
  exitCode: number | null = null;

  emitExit(code: number | null): void {
    this.exitCode = code;
    this.emit("exit", code);
  }
}

function parseRequest(chunk: string): { id: string; method: string } {
  return JSON.parse(chunk) as { id: string; method: string };
}

function emitResponse(child: FakeChild, response: BridgeResponse): void {
  child.stdout.emit("data", Buffer.from(`${JSON.stringify(response)}\n`, "utf-8"));
}

async function withTestDeadline<T>(promise: Promise<T>, timeoutMs = 500): Promise<T> {
  let timeout!: NodeJS.Timeout;
  const deadline = new Promise<never>((_resolve, reject) => {
    timeout = setTimeout(() => reject(new Error("test deadline exceeded")), timeoutMs);
  });
  try {
    return await Promise.race([promise, deadline]);
  } finally {
    clearTimeout(timeout);
  }
}

function createReadyClient(timeoutMs: number | null | "policy" = 20): {
  client: DesktopBridgeClient;
  mutableClient: MutableBridgeClient;
  child: FakeChild;
  session: TestSession;
} {
  const client = new DesktopBridgeClient(bridgeCommand);
  const mutableClient = client as unknown as MutableBridgeClient;
  const child = new FakeChild();
  const session = mutableClient.createSession(
    child as unknown as ChildProcessWithoutNullStreams,
  );
  session.child = child;
  session.startPromise = Promise.resolve();
  mutableClient.session = session;
  if (timeoutMs !== "policy") mutableClient.invokeTimeoutMs = () => timeoutMs;
  mutableClient.attachSessionListeners(session);
  return { client, mutableClient, child, session };
}

describe("DesktopBridgeClient", () => {
  it("uses short health, default, and extended image generation timeouts", () => {
    const client = new DesktopBridgeClient(bridgeCommand) as unknown as MutableBridgeClient;

    assert.equal(client.invokeTimeoutMs("health"), 5_000);
    assert.equal(client.invokeTimeoutMs("roles.list"), 30_000);
    assert.equal(client.invokeTimeoutMs("plugins.communication.services.call"), null);
    assert.equal(client.invokeTimeoutMs("plugin.sample.slow", 300_000), 5 * 60_000);
    assert.equal(
      client.invokeTimeoutMs("plugin.sample.other", 300_000),
      5 * 60_000,
    );
    assert.equal(client.invokeTimeoutMs("plugin.sample.default"), 30_000);
  });

  it("resolves a response and removes its generation-local pending entry", async () => {
    const { client, child, session } = createReadyClient();
    child.stdin.onWrite = (chunk, callback) => {
      callback();
      const request = parseRequest(chunk);
      queueMicrotask(() => emitResponse(child, {
        id: request.id,
        type: "response",
        method: request.method,
        payload: { ok: true },
        error: null,
      }));
    };

    const response = await withTestDeadline(
      client.invoke({ method: "roles.list", payload: {} }),
    );

    assert.deepEqual(response.payload, { ok: true });
    assert.equal(session.pending.size, 0);
  });

  it("returns a structured timeout without stopping the live generation", async () => {
    const { client, child, session } = createReadyClient();

    const response = await withTestDeadline(
      client.invoke({ method: "roles.list", payload: {} }),
    );

    assert.equal(response.error?.code, "bridge_timeout");
    assert.equal(session.pending.size, 0);
    assert.equal(client.isRunning(), true);
    assert.equal(child.killed, false);
  });

  it("waits for a transaction response without scheduling a request deadline", async (context) => {
    const { client, child, session } = createReadyClient(null);
    context.mock.timers.enable({ apis: ["setTimeout"] });
    const pending = client.invoke({ method: "runtime.apply", payload: {} });
    await new Promise<void>((resolvePromise) => setImmediate(resolvePromise));
    context.mock.timers.tick(10 * 60_000);
    await Promise.resolve();
    assert.equal(session.pending.size, 1);
    const request = parseRequest(child.stdin.writes[0]);
    emitResponse(child, { ...request, type: "response", payload: { generation: 2 }, error: null });
    assert.deepEqual((await pending).payload, { generation: 2 });
    assert.equal(session.pending.size, 0);
  });

  it("settles a waiting transaction when its bridge process exits", async () => {
    const { client, child, session } = createReadyClient(null);
    const pending = client.invoke({ method: "runtime.apply", payload: {} });
    await new Promise<void>((resolvePromise) => setImmediate(resolvePromise));
    child.emitExit(1);
    assert.equal((await pending).error?.code, "bridge_exit");
    assert.equal(session.pending.size, 0);
  });

  it("keeps real service work pending past both former deadlines and cleans up its completed response", async (context) => {
    const { client, child, session } = createReadyClient("policy");
    context.mock.timers.enable({ apis: ["setTimeout"] });
    let completed = false;
    const pending = client.invoke({ method: "plugins.communication.services.call", payload: { service: { plugin_id: "neutral", service_id: "slow" }, name: "run", payload: {} } });
    void pending.then(() => { completed = true; });
    await new Promise<void>((resolve) => setImmediate(resolve));
    for (const elapsed of [20_001, 10_000, 5 * 60_000]) {
      context.mock.timers.tick(elapsed);
      await Promise.resolve();
      assert.equal(completed, false);
      assert.equal(session.pending.size, 1);
    }
    const request = parseRequest(child.stdin.writes[0]);
    emitResponse(child, { ...request, type: "response", payload: { value: "provider completed" }, error: null });
    assert.deepEqual((await pending).payload, { value: "provider completed" });
    assert.equal(session.pending.size, 0);
  });

  it("releases a long-running service request when the bridge exits and ignores its late response", async (context) => {
    const { client, child, session } = createReadyClient("policy");
    context.mock.timers.enable({ apis: ["setTimeout"] });
    const pending = client.invoke({ method: "plugins.communication.services.call", payload: {} });
    await new Promise<void>((resolve) => setImmediate(resolve));
    context.mock.timers.tick(60_000);
    const request = parseRequest(child.stdin.writes[0]);
    child.emitExit(1);
    assert.equal((await pending).error?.code, "bridge_exit");
    assert.equal(session.pending.size, 0);
    emitResponse(child, { ...request, type: "response", payload: { late: true }, error: null });
    assert.equal(session.pending.size, 0);
  });

  it("ignores a late response without affecting the next request", async () => {
    const { client, child, session } = createReadyClient();
    const requestIds: string[] = [];
    child.stdin.onWrite = (chunk, callback) => {
      callback();
      const request = parseRequest(chunk);
      requestIds.push(request.id);
      if (requestIds.length === 2) {
        queueMicrotask(() => {
          emitResponse(child, {
            id: requestIds[0],
            type: "response",
            method: "roles.list",
            payload: { stale: true },
            error: null,
          });
          emitResponse(child, {
            id: request.id,
            type: "response",
            method: request.method,
            payload: { current: true },
            error: null,
          });
        });
      }
    };

    const timedOut = await withTestDeadline(
      client.invoke({ method: "roles.list", payload: {} }),
    );
    const current = await client.invoke({ method: "roles.list", payload: {} });

    assert.equal(timedOut.error?.code, "bridge_timeout");
    assert.deepEqual(current.payload, { current: true });
    assert.equal(session.pending.size, 0);
  });

  it("serializes stdin writes until each write callback completes", async () => {
    const { client, child } = createReadyClient(100);
    const callbacks: Array<(error?: Error | null) => void> = [];
    child.stdin.onWrite = (chunk, callback) => {
      callbacks.push(callback);
      const request = parseRequest(chunk);
      emitResponse(child, {
        id: request.id,
        type: "response",
        method: request.method,
        payload: {},
        error: null,
      });
    };

    const first = client.invoke({ method: "roles.list", payload: {} });
    const second = client.invoke({ method: "health", payload: {} });
    await new Promise<void>((resolvePromise) => setImmediate(resolvePromise));
    assert.equal(child.stdin.writes.length, 1);

    callbacks.shift()?.();
    await new Promise<void>((resolvePromise) => setImmediate(resolvePromise));
    assert.equal(child.stdin.writes.length, 2);
    callbacks.shift()?.();
    await Promise.all([first, second]);
  });

  it("keeps a new generation intact when an old exit arrives late", async () => {
    const old = createReadyClient(100);
    const newChild = new FakeChild();
    const newSession = old.mutableClient.createSession(
      newChild as unknown as ChildProcessWithoutNullStreams,
    );
    newSession.child = newChild;
    newSession.startPromise = Promise.resolve();
    old.mutableClient.attachSessionListeners(newSession);
    old.mutableClient.session = newSession;

    old.child.emitExit(0);

    assert.equal(old.mutableClient.session, newSession);
    assert.equal(old.client.isRunning(), true);
  });

  it("ends stdin and waits for a graceful process exit", async () => {
    const { client, mutableClient, child } = createReadyClient(100);
    let killCalled = false;
    mutableClient.gracefulStopTimeoutMs = () => 10;
    mutableClient.killProcessTree = () => {
      killCalled = true;
    };
    child.stdin.onEnd = () => queueMicrotask(() => child.emitExit(0));

    await withTestDeadline(client.stop());

    assert.equal(child.stdin.writableEnded, true);
    assert.equal(killCalled, false);
    assert.equal(client.isRunning(), false);
  });

  it("force-kills a process that ignores graceful EOF", async () => {
    const { client, mutableClient, child } = createReadyClient(100);
    let killedPid: number | null = null;
    mutableClient.gracefulStopTimeoutMs = () => 5;
    mutableClient.forcedStopTimeoutMs = () => 20;
    mutableClient.killProcessTree = (pid) => {
      killedPid = pid;
      child.killed = true;
      child.emitExit(-1);
    };

    await withTestDeadline(client.stop());

    assert.equal(killedPid, child.pid);
    assert.equal(client.isRunning(), false);
  });
});
