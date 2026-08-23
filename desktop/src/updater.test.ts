import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import electronUpdater from "electron-updater";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const updaterModule = pathToFileURL(resolve(dirname(fileURLToPath(import.meta.url)), "updater.ts")).href;

test("packaged main process can import the updater module", () => {
  assert.doesNotThrow(() => {
    execFileSync(
      process.execPath,
      [
        "--import",
        "tsx",
        "--input-type=module",
        "-e",
        `await import(${JSON.stringify(updaterModule)});`,
      ],
      { cwd: repositoryRoot, stdio: "pipe" },
    );
  });
});

test("electron-updater exposes autoUpdater through the packaged ESM import", () => {
  const descriptor = Object.getOwnPropertyDescriptor(electronUpdater, "autoUpdater");
  assert.equal(typeof descriptor?.get, "function");
});
