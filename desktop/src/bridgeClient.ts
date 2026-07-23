import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { EventEmitter } from "node:events";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { BridgeEvent, BridgeRequest, BridgeResponse } from "./shared.js";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..");
const HEALTH_REQUEST_TIMEOUT_MS = 5_000;
const BRIDGE_START_TIMEOUT_MS = 60_000;
const BRIDGE_START_RETRY_DELAY_MS = 250;
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
const IMAGE_GENERATION_TIMEOUT_MS = 5 * 60_000;
const OBSERVATION_TIMEOUT_MS = 2 * 60_000;
const GRACEFUL_STOP_TIMEOUT_MS = 5_000;
const FORCED_STOP_TIMEOUT_MS = 2_000;

type PendingRequest = {
  id: string;
  method: string;
  resolve(response: BridgeResponse): void;
};

type BridgeProcessSession = {
  child: ChildProcessWithoutNullStreams;
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

export class DesktopBridgeClient extends EventEmitter {
  private session: BridgeProcessSession | null = null;
  private lastError: string | null = null;

  private cleanupStaleBridgeProcesses(): void {
    if (process.platform !== "win32") {
      return;
    }
    const result = spawnSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-Command",
        `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.ParentProcessId -eq ${process.pid} -and $_.CommandLine -like '*main.py bridge*' } | Select-Object -ExpandProperty ProcessId`,
      ],
      { encoding: "utf-8" },
    );
    if (result.status !== 0 || !result.stdout.trim()) {
      return;
    }
    for (const rawPid of result.stdout.split(/\r?\n/)) {
      const pid = Number(rawPid.trim());
      if (Number.isFinite(pid) && pid > 0) {
        this.killProcessTree(pid);
      }
    }
  }

  private killProcessTree(pid: number): void {
    if (!Number.isFinite(pid) || pid <= 0) {
      return;
    }
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], {
        stdio: "ignore",
      });
      return;
    }
    try {
      process.kill(pid, "SIGKILL");
    } catch {
      // The process may already have completed its graceful shutdown.
    }
  }

  private createBridgeExitResponse(id: string, method: string, message: string): BridgeResponse {
    return {
      id,
      type: "response",
      method,
      payload: {},
      error: { code: "bridge_exit", message },
    };
  }

  private resolveSessionPending(session: BridgeProcessSession, message: string): void {
    for (const pending of session.pending.values()) {
      pending.resolve(this.createBridgeExitResponse(pending.id, pending.method, message));
    }
    session.pending.clear();
  }

  private invokeTimeoutMs(method: string): number {
    if (method === "health") {
      return HEALTH_REQUEST_TIMEOUT_MS;
    }
    if (method === "novelai.generate" || method === "novelai.regenerateMessageMedia") {
      return IMAGE_GENERATION_TIMEOUT_MS;
    }
    if (method === "observation.analyze") {
      return OBSERVATION_TIMEOUT_MS;
    }
    return DEFAULT_REQUEST_TIMEOUT_MS;
  }

  private gracefulStopTimeoutMs(): number {
    return GRACEFUL_STOP_TIMEOUT_MS;
  }

  private forcedStopTimeoutMs(): number {
    return FORCED_STOP_TIMEOUT_MS;
  }

  private reportSessionFailure(
    session: BridgeProcessSession,
    message: string,
    { kill = false }: { kill?: boolean } = {},
  ): void {
    session.stderrChunks.push(message);
    this.resolveSessionPending(session, message);
    if (this.session === session) {
      this.lastError = message;
    }
    if (!session.exitEmitted) {
      session.exitEmitted = true;
      this.emit("exit", message);
    }
    if (kill) {
      const pid = session.child.pid;
      if (pid) {
        this.killProcessTree(pid);
      }
    }
  }

  private completeSessionExit(
    session: BridgeProcessSession,
    code: number | null,
    processError?: Error,
  ): void {
    if (session.exited) {
      return;
    }
    session.exited = true;
    const stderr = session.stderrChunks.join("").trim();
    const message = processError?.message
      || stderr
      || (session.stopRequested ? "bridge stopped" : `bridge exited with code ${code}`);
    this.resolveSessionPending(session, message);
    if (this.session === session) {
      this.session = null;
      this.lastError = message;
    }
    if ((!session.stopRequested || (code ?? 0) !== 0) && !session.exitEmitted) {
      session.exitEmitted = true;
      this.emit("exit", message);
    }
    session.resolveExit();
    session.child.removeAllListeners();
  }

  private consumeStdout(session: BridgeProcessSession, chunk: Buffer): void {
    session.stdoutBuffer += chunk.toString("utf-8");
    while (true) {
      const index = session.stdoutBuffer.indexOf("\n");
      if (index < 0) {
        return;
      }
      const line = session.stdoutBuffer.slice(0, index).trim();
      session.stdoutBuffer = session.stdoutBuffer.slice(index + 1);
      if (!line) {
        continue;
      }
      let parsed: BridgeResponse | BridgeEvent;
      try {
        parsed = JSON.parse(line) as BridgeResponse | BridgeEvent;
      } catch {
        this.reportSessionFailure(session, `bridge emitted invalid JSON: ${line}`, { kill: true });
        return;
      }
      if (parsed.type === "event") {
        if (this.session === session && !session.stopRequested) {
          this.emit("event", parsed);
        }
        continue;
      }
      session.pending.get(parsed.id)?.resolve(parsed);
    }
  }

  private createSession(child: ChildProcessWithoutNullStreams): BridgeProcessSession {
    let resolveExit!: () => void;
    const exitPromise = new Promise<void>((resolvePromise) => {
      resolveExit = resolvePromise;
    });
    return {
      child,
      pending: new Map(),
      stderrChunks: [],
      stdoutBuffer: "",
      startPromise: Promise.resolve(),
      stopPromise: null,
      writeTail: Promise.resolve(),
      stopRequested: false,
      exited: false,
      exitEmitted: false,
      exitPromise,
      resolveExit,
    };
  }

  private attachSessionListeners(session: BridgeProcessSession): void {
    session.child.stdout.on("data", (chunk: Buffer) => {
      this.consumeStdout(session, chunk);
    });
    session.child.stderr.on("data", (chunk: Buffer) => {
      session.stderrChunks.push(chunk.toString("utf-8"));
    });
    session.child.once("error", (error) => {
      this.completeSessionExit(session, null, error);
    });
    session.child.once("exit", (code) => {
      this.completeSessionExit(session, code);
    });
  }

  private async waitUntilReady(session: BridgeProcessSession): Promise<void> {
    const deadline = Date.now() + BRIDGE_START_TIMEOUT_MS;
    let lastError = "bridge health check failed";
    while (Date.now() < deadline) {
      if (this.session !== session || session.exited) {
        throw new Error(this.lastError || "bridge exited during startup");
      }
      const response = await this.invoke({ method: "health", payload: {} }, true);
      if (!response.error && response.payload?.ok === true) {
        return;
      }
      lastError = response.error?.message || lastError;
      if (response.error?.code === "bridge_exit") {
        throw new Error(lastError);
      }
      await new Promise<void>((resolvePromise) => {
        setTimeout(resolvePromise, BRIDGE_START_RETRY_DELAY_MS);
      });
    }
    throw new Error(lastError);
  }

  start(): Promise<void> {
    const existing = this.session;
    if (existing) {
      if (existing.stopRequested && existing.stopPromise) {
        return existing.stopPromise.then(() => this.start());
      }
      return existing.startPromise;
    }
    this.cleanupStaleBridgeProcesses();
    this.lastError = null;
    const pythonExe = resolve(repoRoot, ".venv", "Scripts", "python.exe");
    if (!existsSync(pythonExe)) {
      throw new Error(`Python bridge runtime not found: ${pythonExe}`);
    }
    const child = spawn(pythonExe, ["main.py", "bridge"], {
      cwd: repoRoot,
      stdio: ["pipe", "pipe", "pipe"],
    });
    const session = this.createSession(child);
    this.session = session;
    this.attachSessionListeners(session);
    session.startPromise = (async () => {
      await new Promise<void>((resolvePromise) => setTimeout(resolvePromise, 200));
      await this.waitUntilReady(session);
    })().catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      this.reportSessionFailure(session, message);
      void this.stopSession(session);
      throw error;
    });
    return session.startPromise;
  }

  private enqueueWrite(
    session: BridgeProcessSession,
    id: string,
    text: string,
  ): Promise<void> {
    const write = session.writeTail.then(async () => {
      if (!session.pending.has(id)) {
        return;
      }
      const child = session.child;
      if (
        this.session !== session
        || session.stopRequested
        || child.killed
        || child.exitCode !== null
        || child.stdin.destroyed
        || child.stdin.writable === false
        || child.stdin.writableEnded
      ) {
        throw new Error(this.lastError || "bridge stopped");
      }
      await new Promise<void>((resolveWrite, rejectWrite) => {
        child.stdin.write(text, (error?: Error | null) => {
          if (error) {
            rejectWrite(error);
            return;
          }
          resolveWrite();
        });
      });
    });
    session.writeTail = write.catch(() => undefined);
    return write;
  }

  async invoke(request: Omit<BridgeRequest, "id">, skipReady = false): Promise<BridgeResponse> {
    if (!this.session) {
      await this.start();
    }
    let session = this.session;
    if (session && !skipReady) {
      await session.startPromise;
      session = this.session;
    }
    if (!session || session.stopRequested) {
      return this.createBridgeExitResponse(
        "bridge-exit",
        request.method,
        this.lastError || "bridge stopped",
      );
    }

    const id = randomUUID();
    const payload: BridgeRequest = { id, method: request.method, payload: request.payload };
    const text = JSON.stringify(payload) + "\n";
    return await new Promise<BridgeResponse>((resolvePromise) => {
      let settled = false;
      let timeout: NodeJS.Timeout | null = null;
      const resolveOnce = (response: BridgeResponse): void => {
        if (settled) {
          return;
        }
        settled = true;
        if (timeout) {
          clearTimeout(timeout);
        }
        session.pending.delete(id);
        resolvePromise(response);
      };
      session.pending.set(id, { id, method: request.method, resolve: resolveOnce });
      const timeoutMs = this.invokeTimeoutMs(request.method);
      timeout = setTimeout(() => {
        resolveOnce({
          id,
          type: "response",
          method: request.method,
          payload: {},
          error: {
            code: "bridge_timeout",
            message: `bridge request timed out after ${timeoutMs}ms`,
          },
        });
      }, timeoutMs);
      timeout.unref();
      void this.enqueueWrite(session, id, text).catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        resolveOnce({
          id,
          type: "response",
          method: request.method,
          payload: {},
          error: { code: "bridge_write_failed", message },
        });
      });
    });
  }

  private stopSession(session: BridgeProcessSession): Promise<void> {
    if (session.stopPromise) {
      return session.stopPromise;
    }
    session.stopRequested = true;
    const message = "bridge stopped";
    this.lastError = message;
    this.resolveSessionPending(session, message);
    session.stopPromise = (async () => {
      if (!session.child.stdin.destroyed && !session.child.stdin.writableEnded) {
        session.child.stdin.end();
      }
      const graceful = await this.waitForSessionExit(session, this.gracefulStopTimeoutMs());
      if (!graceful && !session.exited) {
        const pid = session.child.pid;
        if (pid) {
          this.killProcessTree(pid);
        }
        await this.waitForSessionExit(session, this.forcedStopTimeoutMs());
      }
      if (this.session === session) {
        this.session = null;
      }
    })();
    return session.stopPromise;
  }

  private async waitForSessionExit(
    session: BridgeProcessSession,
    timeoutMs: number,
  ): Promise<boolean> {
    if (session.exited) {
      return true;
    }
    return await new Promise<boolean>((resolvePromise) => {
      let settled = false;
      const resolveOnce = (exited: boolean): void => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timeout);
        resolvePromise(exited);
      };
      const timeout = setTimeout(() => resolveOnce(false), timeoutMs);
      timeout.unref();
      void session.exitPromise.then(() => resolveOnce(true));
    });
  }

  stop(): Promise<void> {
    const session = this.session;
    if (!session) {
      return Promise.resolve();
    }
    return this.stopSession(session);
  }

  async restart(): Promise<void> {
    await this.stop();
    await this.start();
  }

  isRunning(): boolean {
    const session = this.session;
    return Boolean(
      session
      && !session.stopRequested
      && !session.child.killed
      && session.child.exitCode === null,
    );
  }

  getLastError(): string | null {
    return this.lastError;
  }
}
