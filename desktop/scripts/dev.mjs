import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const require = createRequire(import.meta.url);
const electronExe = require("electron");
const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const rendererConfig = resolve(desktopRoot, "renderer", "vite.config.ts");
const userDataDir = resolve(desktopRoot, ".dev-user-data");

const server = await createServer({
  configFile: rendererConfig,
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
});

let electronProc;
let shuttingDown = false;

async function shutdown(code = 0) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  if (electronProc && !electronProc.killed) {
    electronProc.kill();
  }
  await server.close();
  process.exit(code);
}

process.on("SIGINT", () => {
  void shutdown(0);
});

process.on("SIGTERM", () => {
  void shutdown(0);
});

await server.listen();
server.printUrls();

const devServerUrl = server.resolvedUrls?.local[0];
if (!devServerUrl) {
  throw new Error("Vite dev server did not expose a local URL.");
}

electronProc = spawn(electronExe, ["."], {
  cwd: desktopRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    MIRA_RENDERER_DEV_SERVER_URL: devServerUrl,
    MIRA_DESKTOP_USER_DATA_DIR: userDataDir,
  },
});

electronProc.on("exit", (code) => {
  void shutdown(code ?? 0);
});
