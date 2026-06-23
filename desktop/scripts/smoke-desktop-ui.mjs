import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const electronExe = resolve(desktopRoot, "node_modules", "electron", "dist", "electron.exe");

const proc = spawn(
  electronExe,
  ["."],
  {
    cwd: desktopRoot,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      MIRA_DESKTOP_UI_SMOKE: "1",
      MIRA_DESKTOP_PICK_IMAGES_FIXTURE: "1",
    },
  },
);

let settled = false;
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
  const marker = "[desktop-ui-smoke] ";
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
      if (parsed?.ok === true && String(parsed?.hero || "").includes("Smoke UI Role")) {
        finish(0, "desktop ui smoke ok");
        return;
      }
      finish(1, `desktop ui smoke payload invalid: ${payload}\nSTDERR:\n${stderr}`);
    } catch {
      finish(1, `desktop ui smoke invalid JSON: ${payload}\nSTDERR:\n${stderr}`);
    }
  }
});

proc.on("exit", (code) => {
  finish(1, `desktop ui exited before smoke completed (${code ?? "unknown"})\nSTDERR:\n${stderr}\nSTDOUT:\n${stdout}`);
});

setTimeout(() => {
  finish(1, `desktop ui smoke timed out\nSTDERR:\n${stderr}\nSTDOUT:\n${stdout}`);
}, 45000);
