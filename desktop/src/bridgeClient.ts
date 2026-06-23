import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { BridgeEvent, BridgeRequest, BridgeResponse } from "./shared.js";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..");

export class DesktopBridgeClient extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, (value: BridgeResponse) => void>();
  private stderrChunks: string[] = [];
  private stopRequested = false;
  private lastError: string | null = null;
  private startPromise: Promise<void> | null = null;

  private resolvePendingWithExit(message: string): void {
    for (const [, resolvePending] of this.pending) {
      resolvePending({
        id: "bridge-exit",
        type: "response",
        method: "bridge.exit",
        payload: {},
        error: { code: "bridge_exit", message },
      });
    }
    this.pending.clear();
  }

  private async waitUntilReady(): Promise<void> {
    const response = await this.invoke({
      method: "health",
      payload: {},
    }, true);
    if (response.error || response.payload?.ok !== true) {
      throw new Error(response.error?.message || "bridge health check failed");
    }
  }

  start(): Promise<void> {
    if (this.child) {
      return this.startPromise ?? Promise.resolve();
    }
    this.stopRequested = false;
    this.stderrChunks = [];
    this.lastError = null;
    const pythonExe = resolve(repoRoot, ".venv", "Scripts", "python.exe");
    if (!existsSync(pythonExe)) {
      throw new Error(`Python bridge runtime not found: ${pythonExe}`);
    }
    this.child = spawn(
      pythonExe,
      ["main.py", "bridge"],
      {
        cwd: repoRoot,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    this.startPromise = (async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 200));
      await this.waitUntilReady();
    })();

    let buffer = "";
    this.child.stdout.on("data", (chunk: Buffer) => {
      buffer += chunk.toString("utf-8");
      while (true) {
        const index = buffer.indexOf("\n");
        if (index < 0) break;
        const line = buffer.slice(0, index).trim();
        buffer = buffer.slice(index + 1);
        if (!line) continue;
        let parsed: BridgeResponse | BridgeEvent;
        try {
          parsed = JSON.parse(line) as BridgeResponse | BridgeEvent;
        } catch (error) {
          const message = `bridge emitted invalid JSON: ${line}`;
          this.lastError = message;
          this.stderrChunks.push(message);
          this.resolvePendingWithExit(message);
          this.emit("exit", message);
          this.child?.kill();
          return;
        }
        if (parsed.type === "event") {
          this.emit("event", parsed);
          continue;
        }
        const resolvePending = this.pending.get(parsed.id);
        if (resolvePending) {
          this.pending.delete(parsed.id);
          resolvePending(parsed);
        }
      }
    });

    this.child.stderr.on("data", (chunk: Buffer) => {
      this.stderrChunks.push(chunk.toString("utf-8"));
    });

    this.child.on("exit", (code) => {
      const child = this.child;
      const message = this.stderrChunks.join("").trim() || `bridge exited with code ${code}`;
      this.lastError = message;
      this.resolvePendingWithExit(message);
      this.child = null;
      if (!this.stopRequested || (code ?? 0) !== 0) {
        this.emit("exit", message);
      }
      child?.removeAllListeners();
      this.startPromise = null;
    });

    return this.startPromise;
  }

  async invoke(request: Omit<BridgeRequest, "id">, skipReady = false): Promise<BridgeResponse> {
    if (!this.child) {
      await this.start();
    } else if (!skipReady && this.startPromise) {
      await this.startPromise;
    }
    const id = randomUUID();
    const payload: BridgeRequest = {
      id,
      method: request.method,
      payload: request.payload,
    };
    const text = JSON.stringify(payload) + "\n";

    return await new Promise<BridgeResponse>((resolvePending) => {
      this.pending.set(id, resolvePending);
      this.child?.stdin.write(text);
    });
  }

  stop(): void {
    this.stopRequested = true;
    const message = "bridge stopped";
    this.lastError = message;
    this.resolvePendingWithExit(message);
    this.child?.kill();
    this.child = null;
    this.startPromise = null;
  }

  async restart(): Promise<void> {
    this.stop();
    await this.start();
  }

  isRunning(): boolean {
    return this.child !== null;
  }

  getLastError(): string | null {
    return this.lastError;
  }
}
