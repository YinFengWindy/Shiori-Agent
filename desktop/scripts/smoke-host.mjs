import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..");
const pythonExe = resolve(repoRoot, ".venv", "Scripts", "python.exe");

const proc = spawn(
  pythonExe,
  ["main.py", "bridge"],
  {
    cwd: repoRoot,
    stdio: ["pipe", "pipe", "pipe"],
  },
);

let settled = false;
let stderr = "";
let stdoutBuffer = "";
const pending = new Map();

function finish(code, message) {
  if (settled) return;
  settled = true;
  if (message) {
    console.log(message);
  }
  try {
    proc.kill();
  } catch {}
  process.exit(code);
}

proc.stderr.on("data", (chunk) => {
  stderr += chunk.toString("utf-8");
});

proc.stdout.on("data", (chunk) => {
  stdoutBuffer += chunk.toString("utf-8");
  while (true) {
    const lineEnd = stdoutBuffer.indexOf("\n");
    if (lineEnd < 0) break;
    const line = stdoutBuffer.slice(0, lineEnd).trim();
    stdoutBuffer = stdoutBuffer.slice(lineEnd + 1);
    if (!line) continue;
    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch {
      finish(1, `invalid host bridge stdout: ${line}\n${stderr}`);
      return;
    }
    const resolver = pending.get(parsed.id);
    if (resolver) {
      pending.delete(parsed.id);
      resolver(parsed);
    }
  }
});

proc.on("exit", (code) => {
  finish(1, `host bridge exited early (${code ?? "unknown"})\n${stderr}`);
});

function request(method, payload) {
  const id = randomUUID();
  return new Promise((resolve) => {
    pending.set(id, resolve);
    proc.stdin.write(`${JSON.stringify({ id, method, payload })}\n`);
  });
}

setTimeout(() => {
  finish(1, `host bridge smoke timed out\n${stderr}`);
}, 60000);

(async () => {
  const health = await request("health", {});
  if (health.error || health.payload?.ok !== true) {
    finish(1, `health failed: ${JSON.stringify(health)}\n${stderr}`);
    return;
  }

  const roles = await request("roles.list", {});
  if (roles.error || !Array.isArray(roles.payload?.roles)) {
    finish(1, `roles.list failed: ${JSON.stringify(roles)}\n${stderr}`);
    return;
  }

  finish(0, "desktop host bridge rpc ok");
})();
