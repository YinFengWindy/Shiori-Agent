import assert from "node:assert/strict";
import { mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Script } from "node:vm";
import test from "node:test";
import { createServer } from "vite";
import { classicWorkerUrls } from "./classic-worker-urls.mjs";

test("dev worker URL executes imports as a classic script and reloads changed dependencies", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "classic-worker-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, "value.ts"), "export const value: number = 42;", "utf8");
  await writeFile(join(root, "worker.ts"), 'import { value } from "./value"; postMessage(value);', "utf8");
  const server = await createServer({
    root, configFile: false, logLevel: "silent", plugins: [classicWorkerUrls()],
    server: { host: "127.0.0.1", port: 0, preTransformRequests: false },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  t.after(() => server.close());
  await server.listen();
  const base = server.resolvedUrls.local[0];
  const module = await server.ssrLoadModule("/worker.ts?worker&url");
  const runWorker = async () => {
    const response = await fetch(new URL(module.default, base));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const messages = [];
    new Script(await response.text()).runInNewContext({ postMessage: (message) => messages.push(message) });
    return messages;
  };
  assert.deepEqual(await runWorker(), [42]);
  await writeFile(join(root, "value.ts"), "export const value: number = 73;", "utf8");
  assert.deepEqual(await runWorker(), [73]);
  assert.equal((await fetch(new URL("/@shiori-classic-worker/unregistered.js", base))).status, 404);
});
