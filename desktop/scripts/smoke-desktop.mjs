import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const devScript = resolve(here, "dev.mjs");

const proc = spawn(
  process.execPath,
  [devScript],
  {
    cwd: desktopRoot,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      MIRA_DESKTOP_SMOKE: "1",
    },
  },
);

let settled = false;
let awaitingExplicitQuit = false;
let stderr = "";
let stdout = "";

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
  stdout += chunk.toString("utf-8");
  const marker = "[desktop-smoke] ";
  const lines = stdout
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  for (const line of lines) {
    if (!line.startsWith(marker)) continue;
    const payload = line.slice(marker.length).trim();
    if (!payload.startsWith("{")) {
      continue;
    }
    try {
      const parsed = JSON.parse(payload);
      if (
        parsed?.status?.running
        && parsed?.health?.payload?.ok === true
        && Array.isArray(parsed?.roles?.payload?.roles)
        && parsed?.restarted?.ok === true
        && parsed?.restarted?.running === true
        && parsed?.healthAfterRestart?.payload?.ok === true
        && parsed?.createdRole?.payload?.role?.id
        && parsed?.openedSession?.payload?.session?.key === `role:${parsed.createdRole.payload.role.id}`
        && parsed?.deletedRole?.payload?.deleted === true
        && parsed?.deletedRole?.payload?.session_deleted === true
        && parsed?.trayLifecycle?.ok === true
        && parsed?.trayLifecycle?.hiddenAfterClose === true
        && parsed?.trayLifecycle?.visibleAfterRestore === true
        && parsed?.trayLifecycle?.bridgeRunningAfterClose === true
        && parsed?.trayLifecycle?.bridgeRunningAfterRestore === true
      ) {
        awaitingExplicitQuit = true;
        return;
      }
      finish(1, `desktop smoke payload invalid: ${payload}\nSTDERR:\n${stderr}`);
    } catch {
      finish(1, `desktop smoke invalid JSON: ${payload}\nSTDERR:\n${stderr}`);
    }
  }
});

proc.on("exit", (code) => {
  if (awaitingExplicitQuit && code === 0) {
    finish(0, "desktop renderer bridge smoke ok");
    return;
  }
  finish(1, `desktop exited before smoke completed (${code ?? "unknown"})\nSTDERR:\n${stderr}\nSTDOUT:\n${stdout}`);
});

setTimeout(() => {
  finish(1, `desktop smoke timed out\nSTDERR:\n${stderr}\nSTDOUT:\n${stdout}`);
}, 45000);
