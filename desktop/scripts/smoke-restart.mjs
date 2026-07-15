import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DesktopBridgeClient } from "../dist/bridgeClient.js";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
process.chdir(desktopRoot);

const bridge = new DesktopBridgeClient();
const timeout = setTimeout(() => {
  console.error("restart smoke timed out");
  process.exit(1);
}, 120000);

try {
  console.log("restart smoke: starting bridge");
  await bridge.start();
  console.log("restart smoke: first health");
  const first = await bridge.invoke({ method: "health", payload: {} });
  if (first.error || first.payload?.ok !== true) {
    throw new Error(`initial health failed: ${JSON.stringify(first)}`);
  }

  console.log("restart smoke: restarting bridge");
  await bridge.restart();
  console.log("restart smoke: second health");
  const second = await bridge.invoke({ method: "health", payload: {} });
  if (second.error || second.payload?.ok !== true) {
    throw new Error(`health after restart failed: ${JSON.stringify(second)}`);
  }

  console.log("desktop bridge restart ok");
  clearTimeout(timeout);
} finally {
  await bridge.stop();
}
