import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { createServer as createNetServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const require = createRequire(import.meta.url);
const electronExe = require("electron");
const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const rendererConfig = resolve(desktopRoot, "renderer", "vite.config.ts");
const userDataDir = resolve(desktopRoot, ".dev-user-data");
const preferredPort = Number(process.env.MIRA_RENDERER_DEV_SERVER_PORT || "5173");

async function canListen(port) {
  return await new Promise((resolve) => {
    const probe = createNetServer();
    probe.once("error", () => resolve(false));
    probe.listen(port, "127.0.0.1", () => {
      probe.close(() => resolve(true));
    });
  });
}

async function resolveRendererPort(startPort, attempts = 20) {
  for (let port = startPort; port < startPort + attempts; port += 1) {
    if (await canListen(port)) {
      return port;
    }
  }
  throw new Error(`No available renderer dev port found starting from ${startPort}.`);
}

const rendererPort = await resolveRendererPort(preferredPort);

const server = await createServer({
  configFile: rendererConfig,
  server: {
    host: "127.0.0.1",
    port: rendererPort,
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
