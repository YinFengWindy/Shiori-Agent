const { app } = require("electron");
const { dirname, resolve } = require("node:path");
if (!process.env.SHIORI_QA_HOME || !process.env.SHIORI_DESKTOP_USER_DATA_DIR) throw new Error("Isolated QA paths are required");
app.setPath("home", resolve(process.env.SHIORI_QA_HOME));
app.setPath("userData", resolve(process.env.SHIORI_DESKTOP_USER_DATA_DIR));
(async () => {
  // Test-only frozen-runtime selection; production still resolves the repository .venv.
  if (process.env.SHIORI_QA_RUNTIME_EXE) {
    const { DesktopBridgeClient } = await import("../../dist/bridge/bridgeClient.js");
    const start = DesktopBridgeClient.prototype.start;
    DesktopBridgeClient.prototype.start = function (...args) {
      const executable = resolve(process.env.SHIORI_QA_RUNTIME_EXE);
      this.command = { executable, cwd: dirname(executable), args: this.command.args.filter((arg) => arg !== "main.py") };
      return start.apply(this, args);
    };
  }
  await import("../../dist/main.js");
})().catch((error) => { console.error(error); app.exit(1); });
