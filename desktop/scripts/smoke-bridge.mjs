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
      finish(1, `invalid bridge stdout: ${line}\n${stderr}`);
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
  finish(1, `bridge exited early (${code ?? "unknown"})\n${stderr}`);
});

function request(method, payload) {
  const id = randomUUID();
  const text = `${JSON.stringify({ id, method, payload })}\n`;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    proc.stdin.write(text);
  });
}

setTimeout(() => {
  finish(1, `bridge smoke timed out\n${stderr}`);
}, 12000);

(async () => {
  const health = await request("health", {});
  if (health.error || health.payload?.ok !== true) {
    finish(1, `health failed: ${JSON.stringify(health)}\n${stderr}`);
    return;
  }

  const role = await request("roles.create", {
    name: "Smoke Role",
    description: "bridge smoke role",
    system_prompt: "you are smoke role",
  });
  if (role.error || !role.payload?.role?.id) {
    finish(1, `roles.create failed: ${JSON.stringify(role)}\n${stderr}`);
    return;
  }

  const roleId = role.payload.role.id;
  const session = await request("session.openByRole", { role_id: roleId });
  if (session.error || session.payload?.session?.key !== `desktop:role:${roleId}`) {
    finish(1, `session.openByRole failed: ${JSON.stringify(session)}\n${stderr}`);
    return;
  }

  const deletion = await request("roles.delete", { role_id: roleId });
  if (deletion.error || deletion.payload?.deleted !== true) {
    finish(1, `roles.delete failed: ${JSON.stringify(deletion)}\n${stderr}`);
    return;
  }

  finish(0, "bridge lifecycle ok");
})();
